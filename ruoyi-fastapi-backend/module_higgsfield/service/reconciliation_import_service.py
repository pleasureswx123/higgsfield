"""内部导入事务：调用方已校验批次文件；不做网络 IO 或自动确认费用。"""
from module_higgsfield.dao.reconciliation_dao import ReconciliationDao as Dao
from module_higgsfield.entity.do.reconciliation_do import HfReconciliationLine, HfReconciliationObservation
from module_higgsfield.service.reconciliation_parser_service import ReconciliationParserService as Parser
from module_higgsfield.service.project_workspace_service import WorkspaceService
from utils.time_util import TimezoneUtil


class ReconciliationImportService:
    @staticmethod
    def validate(rows):
        if not rows or len(rows) > 100000:
            Parser.fail(0, '账单明细为空或超过导入限制')
        previous = 0
        clean = []
        for row in rows:
            if type(row.line_no) is not int or row.line_no <= previous:
                Parser.fail(0, '账单行号必须严格递增且不能重复')
            if set(row.raw_line) != set(Parser.columns):
                Parser.fail(row.line_no, '账单证据字段不符合白名单')
            current = Parser.row(row.line_no, [row.raw_line[key] for key in Parser.columns])
            if (current.external_line_key, current.currency, current.amount) != (row.external_line_key, row.currency, row.amount):
                Parser.fail(row.line_no, '账单解析值与原始证据不一致')
            clean.append(current)
            previous = row.line_no
        return clean

    @classmethod
    async def apply(cls, db, batch_id, rows):
        try:
            rows = cls.validate(rows)
            batch = await Dao.batch(db, batch_id)
            if batch is None:
                WorkspaceService.conflict('RECONCILIATION_NOT_FOUND', '对账批次不存在')
            account_id = batch.account_id
            await Dao.lock_account(db, account_id)
            batch = await Dao.batch(db, batch_id, lock=True)
            if batch.account_id != account_id:
                WorkspaceService.conflict('RECONCILIATION_STATE_CONFLICT', '对账批次账号发生变化')
            existing = await Dao.observations(db, batch_id)
            if existing:
                if [(row.line_no, row.raw_line) for row in existing] != [(row.line_no, row.raw_line) for row in rows]:
                    WorkspaceService.conflict('RECONCILIATION_EVIDENCE_CONFLICT', '已导入批次不能更换原始行证据')
                await db.commit()
                return False
            if batch.status != '0':
                WorkspaceService.conflict('RECONCILIATION_STATE_CONFLICT', '仅待解析批次允许首次导入')
            now = TimezoneUtil.utc_now()
            audit = dict(create_by=batch.create_by, update_by=batch.create_by, create_time=now, update_time=now)
            disputed = set()
            for parsed in rows:
                line = await Dao.line(db, account_id, parsed.external_line_key)
                if line is None:
                    line = await Dao.add(db, HfReconciliationLine, batch_id=batch_id, account_id=account_id,
                        line_no=parsed.line_no, external_line_key=parsed.external_line_key, currency=parsed.currency,
                        amount=parsed.amount, raw_line=parsed.raw_line, status='0', revision=1, **audit)
                    outcome = 'original'
                elif (line.accepted_currency or line.currency) == parsed.currency and (
                    line.accepted_amount if line.accepted_amount is not None else line.amount) == parsed.amount:
                    outcome = 'duplicate'
                else:
                    outcome = 'conflict'
                    # 新冲突证据必须使旧人工处理快照失效，即使已经处于差异状态。
                    line.status = '3'
                    line.revision += 1
                    line.update_by, line.update_time = batch.create_by, now
                if line.status == '3':
                    disputed.add(line.line_id)
                await Dao.add(db, HfReconciliationObservation, batch_id=batch_id, line_no=parsed.line_no,
                    canonical_line_id=line.line_id, outcome=outcome, raw_line=parsed.raw_line, **audit)
            # 批次状态由所引用账单项的当前状态汇总，重复证据不撤销既有人工确认。
            await Dao.flush(db)
            states = await Dao.batch_line_states(db, batch_id)
            batch.status = '3' if '3' in states else '2' if states == ['2'] else '1'
            batch.revision += 1
            batch.update_by, batch.update_time = batch.create_by, now
            await Dao.flush(db)
            # 新修订发现冲突后，所有引用该账单项的批次都失去旧确认状态。
            for affected in await Dao.affected_batches(db, disputed):
                if affected.batch_id == batch_id:
                    continue
                if affected.account_id != account_id:
                    WorkspaceService.conflict('RECONCILIATION_ACCOUNT_CONFLICT', '账单证据存在跨账号关联')
                affected.status = '3'
                affected.revision += 1
                affected.update_by, affected.update_time = batch.create_by, now
            await db.commit()
            return True
        except BaseException:
            await db.rollback()
            raise
