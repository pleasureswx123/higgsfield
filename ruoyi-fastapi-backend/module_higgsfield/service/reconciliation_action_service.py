"""人工账单匹配与确认只改变对账状态，不自动调整估值。"""
from module_higgsfield.dao.reconciliation_dao import ReconciliationDao as Dao
from module_higgsfield.entity.do.audit_do import HfAuditLog
from module_higgsfield.service.admin_scope_service import AdminScopeService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService
from module_higgsfield.service.reconciliation_parser_service import ReconciliationParserService


class ReconciliationActionService:
    @staticmethod
    def result(line):
        return {'id': str(line.line_id), 'batchId': str(line.batch_id), 'lineNo': line.line_no,
            'externalLineKey': line.external_line_key,
            'subjectId': str(line.subject_id) if line.subject_id else None,
            'currency': line.currency, 'amount': format(line.amount, '.10f'),
            'acceptedObservationId': str(line.accepted_observation_id) if line.accepted_observation_id else None,
            'acceptedCurrency': line.accepted_currency,
            'acceptedAmount': format(line.accepted_amount, '.10f') if line.accepted_amount is not None else None,
            'status': {'0': 'unmatched', '1': 'matched', '2': 'confirmed', '3': 'disputed'}[line.status],
            'revision': str(line.revision)}

    @classmethod
    async def save(cls, db, user, line_id, action, payload, key):
        if action not in ('match', 'confirm', 'resolve'):
            raise ValueError('不支持的对账动作')
        path, prefix = f'/reconciliation-lines/{line_id}/{action}', '/api/admin/v1'
        data = payload.model_dump(by_alias=True)
        try:
            await AdminScopeService.global_access(db, user, 'billing:reconcile')
            await WriteService.lock(db, user, path, key, api_prefix=prefix)
            replay = await WriteService.replay(db, user, path, key, data, api_prefix=prefix)
            if replay:
                await db.commit()
                return replay, True
            line = await Dao.line_by_id(db, line_id)
            if line is None:
                WorkspaceService.conflict('RECONCILIATION_LINE_NOT_FOUND', '账单项不存在')
            account_id = line.account_id
            await Dao.lock_account(db, account_id)
            line = await Dao.line_by_id(db, line_id, lock=True)
            if line.account_id != account_id:
                WorkspaceService.conflict('RECONCILIATION_ACCOUNT_CONFLICT', '账单项账号发生变化')
            WorkspaceService.check_revision(line, payload.revision)
            if action == 'resolve' and line.status != '3':
                WorkspaceService.conflict('RECONCILIATION_STATE_CONFLICT', '仅差异状态允许选择采用证据')
            if action != 'resolve' and line.status in ('2', '3'):
                WorkspaceService.conflict('RECONCILIATION_STATE_CONFLICT', '已确认或有差异账单项不能直接重新匹配或确认')
            if action == 'confirm' and (line.status != '1' or line.subject_id is None):
                WorkspaceService.conflict('RECONCILIATION_NOT_MATCHED', '必须先匹配计费对象再确认账单项')
            subject_id = int(payload.subject_id) if action in ('match', 'resolve') else line.subject_id
            subject = await Dao.subject(db, subject_id)
            if subject is None or subject.account_id != account_id:
                WorkspaceService.conflict('RECONCILIATION_ACCOUNT_CONFLICT', '计费对象不存在或不属于同一供应商账号')
            before = cls.result(line)
            if action == 'resolve':
                observation = await Dao.observation(db, int(payload.observation_id))
                if observation is None or observation.canonical_line_id != line_id:
                    WorkspaceService.conflict('RECONCILIATION_EVIDENCE_MISMATCH', '所选观察证据不属于当前账单项')
                evidence_batch = await Dao.batch(db, observation.batch_id)
                if evidence_batch is None or evidence_batch.account_id != account_id or evidence_batch.import_error is not None:
                    WorkspaceService.conflict('RECONCILIATION_EVIDENCE_MISMATCH', '所选证据的批次归属或解析状态异常')
                parsed = ReconciliationParserService.row(observation.line_no,
                    [observation.raw_line.get(column) for column in ReconciliationParserService.columns])
                if parsed.external_line_key != line.external_line_key:
                    WorkspaceService.conflict('RECONCILIATION_EVIDENCE_MISMATCH', '所选证据的账单身份不一致')
                line.accepted_observation_id = observation.observation_id
                line.accepted_currency, line.accepted_amount = parsed.currency, parsed.amount
            audit = WriteService.audit(user)
            line.subject_id = subject_id
            line.status = '2' if action == 'confirm' else '1'
            line.revision += 1
            line.update_by, line.update_time = user.user.user_name, audit['update_time']
            await Dao.flush(db)
            batches = await Dao.affected_batches(db, [line_id])
            if not batches:
                WorkspaceService.conflict('RECONCILIATION_EVIDENCE_MISSING', '账单项缺少原始文件观察证据')
            for batch in batches:
                if batch.account_id != account_id or batch.import_error is not None:
                    WorkspaceService.conflict('RECONCILIATION_ACCOUNT_CONFLICT', '批次账号或文件解析状态异常')
                states = await Dao.batch_line_states(db, batch.batch_id)
                batch.status = '3' if '3' in states else '2' if states == ['2'] else '1'
                batch.revision += 1
                batch.update_by, batch.update_time = user.user.user_name, audit['update_time']
            result = cls.result(line)
            await Dao.add(db, HfAuditLog, actor_id=user.user.user_id, actor_kind='user',
                object_type='reconciliation_line', object_id=str(line_id), action=action,
                request_id=WriteService.digest({'path': path, 'key': key}),
                before_after={'before': before, 'after': result, 'reason': payload.reason}, **audit)
            return await WriteService.finish(db, user, path, key, data, result,
                'reconciliation_line', line_id, api_prefix=prefix)
        except BaseException:
            await db.rollback()
            raise
