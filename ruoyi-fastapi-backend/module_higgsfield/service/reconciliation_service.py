"""对账受理原子绑定本人上传；HTTP 请求不解析文件或修改估值。"""
from module_higgsfield.dao.reconciliation_dao import ReconciliationDao as Dao
from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.entity.do.reconciliation_do import HfReconciliationBatch
from module_higgsfield.entity.do.asset_do import HfUploadBinding
from module_higgsfield.entity.do.audit_do import HfAuditLog
from module_higgsfield.service.admin_scope_service import AdminScopeService
from module_higgsfield.service.document_upload_service import DocumentUploadService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService
from common.vo import PageModel
from module_higgsfield.service.stored_media_service import StoredMediaService
from module_higgsfield.service.reconciliation_parser_service import ReconciliationParserService as Parser


class ReconciliationService:
    @staticmethod
    def attachment(context):
        """只返回可公开元数据，异常关联不阻断批次诊断查看。"""
        if context is None:
            return None
        batch, file, upload = context
        if (file.state != '1' or upload.state != '3' or upload.purpose != 'reconciliation'
                or upload.project_id is not None or upload.completed_file_id != file.file_id
                or upload.byte_size != file.byte_size or upload.verified_sha256 != file.sha256
                or batch.file_hash != file.sha256 or file.mime_type not in Parser.mime_types
                or upload.declared_mime_type != file.mime_type):
            return None
        return {'fileName': upload.file_name, 'mimeType': file.mime_type,
            'byteSize': str(file.byte_size), 'sha256': file.sha256,
            'downloadUrl': f'/api/admin/v1/reconciliations/{batch.batch_id}/attachment/download'}

    @classmethod
    async def download(cls, db, user, batch_id, range_header=None, head=False, storage=None):
        await AdminScopeService.global_access(db, user, 'billing:read')
        if await Dao.batch(db, batch_id) is None:
            WorkspaceService.conflict('RECONCILIATION_NOT_FOUND', '对账批次不存在')
        context = await Dao.file_context(db, batch_id)
        metadata = cls.attachment(context)
        if metadata is None:
            WorkspaceService.conflict('FILE_NOT_READY', '账单文件不可用或关联不一致')
        file = context[1]
        return await StoredMediaService.stream(db, file.storage_key, file.byte_size, file.mime_type,
            metadata['fileName'], range_header, True, head, storage)

    @staticmethod
    def result(batch, counts):
        error = None
        if batch.import_error is not None:
            line_no = batch.import_error.get('lineNo', 0)
            line_no = line_no if type(line_no) is int and 0 <= line_no <= 2147483647 else 0
            error = {'code': 'RECONCILIATION_FILE_INVALID', 'lineNo': line_no,
                'message': '账单文件或格式校验失败，请核对原始文件及标准模板'}
        return {'id': str(batch.batch_id), 'accountId': str(batch.account_id),
            'periodStart': batch.period_start, 'periodEnd': batch.period_end,
            'status': {'0': 'imported', '1': 'matching', '2': 'confirmed', '3': 'disputed'}[batch.status],
            'importState': 'failed' if error else 'pending' if batch.status == '0' else 'processed',
            'importError': error, 'revision': str(batch.revision), 'counts': counts, 'createTime': batch.create_time}

    @classmethod
    async def listing(cls, db, user, query):
        await AdminScopeService.global_access(db, user, 'billing:read')
        batches, total = await Dao.page(db, query)
        counts = await Dao.batch_counts(db, [batch.batch_id for batch in batches])
        return PageModel(rows=[cls.result(batch, counts.get(batch.batch_id,
            {'total': 0, 'matched': 0, 'disputed': 0})) for batch in batches],
            total=total, pageNum=query.page_num, pageSize=query.page_size,
            hasNext=query.page_num*query.page_size < total)

    @classmethod
    async def lines(cls, db, user, batch_id, query):
        await AdminScopeService.global_access(db, user, 'billing:read')
        if await Dao.batch(db, batch_id) is None:
            WorkspaceService.conflict('RECONCILIATION_NOT_FOUND', '对账批次不存在')
        records, total = await Dao.line_page(db, batch_id, query)
        rows = []
        for observation, line in records:
            # 返回当前文件观察值和正式账单项，不能把冲突文件中的新金额冒充首次金额。
            evidence = {key: observation.raw_line.get(key) for key in ('externalLineKey', 'currency', 'amount')}
            rows.append({'id': str(line.line_id), 'batchId': str(batch_id),
                'canonicalBatchId': str(line.batch_id), 'observationId': str(observation.observation_id),
                'lineNo': observation.line_no, 'externalLineKey': line.external_line_key,
                'subjectId': str(line.subject_id) if line.subject_id is not None else None,
                'currency': line.currency, 'amount': format(line.amount, '.10f'),
                'acceptedObservationId': str(line.accepted_observation_id) if line.accepted_observation_id else None,
                'acceptedCurrency': line.accepted_currency,
                'acceptedAmount': format(line.accepted_amount, '.10f') if line.accepted_amount is not None else None,
                'status': {'0': 'unmatched', '1': 'matched', '2': 'confirmed', '3': 'disputed'}[line.status],
                'revision': str(line.revision), 'outcome': observation.outcome, 'sourceEvidence': evidence})
        return PageModel(rows=rows, total=total, pageNum=query.page_num, pageSize=query.page_size,
            hasNext=query.page_num*query.page_size < total)

    @classmethod
    async def get(cls, db, user, batch_id):
        await AdminScopeService.global_access(db, user, 'billing:read')
        batch = await Dao.batch(db, batch_id)
        if batch is None:
            WorkspaceService.conflict('RECONCILIATION_NOT_FOUND', '对账批次不存在')
        result = cls.result(batch, await Dao.counts(db, batch_id))
        result['attachment'] = cls.attachment(await Dao.file_context(db, batch_id))
        return result

    @classmethod
    async def create(cls, db, user, payload, key):
        path, prefix = '/reconciliations', '/api/admin/v1'
        data = payload.model_dump(by_alias=True, mode='json')
        try:
            await AdminScopeService.global_access(db, user, 'billing:reconcile')
            await WriteService.lock(db, user, path, key, api_prefix=prefix)
            replay = await WriteService.replay(db, user, path, key, data, api_prefix=prefix)
            if replay:
                await db.commit()
                return replay, True
            account_id = int(payload.account_id)
            await Dao.lock_account(db, account_id)
            if await Dao.account(db, account_id) is None:
                WorkspaceService.conflict('PROVIDER_ACCOUNT_NOT_FOUND', '供应商账号不存在')
            upload = await DocumentUploadService.authorize(db, user, int(payload.upload_id), write=True)
            if upload.purpose != 'reconciliation':
                WorkspaceService.conflict('UPLOAD_PURPOSE_MISMATCH', '对账必须使用对账用途的管理上传')
            if upload.state != '3':
                WorkspaceService.conflict('UPLOAD_NOT_READY', '账单文件尚未完成校验')
            if await AssetDao.binding(db, upload.upload_id):
                WorkspaceService.conflict('UPLOAD_ALREADY_BOUND', '上传已绑定正式记录，请使用原受理结果')
            file = await AssetDao.file(db, upload.completed_file_id)
            if (file is None or file.state != '1' or file.sha256 != upload.verified_sha256
                    or file.byte_size != upload.byte_size or file.mime_type != upload.declared_mime_type):
                WorkspaceService.conflict('FILE_NOT_READY', '账单文件不可用或元数据不一致')
            if file.mime_type not in Parser.mime_types:
                WorkspaceService.conflict('RECONCILIATION_FORMAT_UNSUPPORTED', '对账导入支持标准 CSV 或 XLSX 模板')
            if await Dao.duplicate_file(db, account_id, payload.period_start, payload.period_end, file.sha256):
                WorkspaceService.conflict('RECONCILIATION_FILE_DUPLICATE', '该账号账期的同一文件已受理')
            audit = WriteService.audit(user)
            batch = await Dao.add(db, HfReconciliationBatch, account_id=account_id,
                period_start=payload.period_start, period_end=payload.period_end,
                source_file_id=file.file_id, file_hash=file.sha256, status='0', revision=1, **audit)
            await Dao.add(db, HfUploadBinding, session_id=upload.upload_id,
                reconciliation_batch_id=batch.batch_id, bound_by=user.user.user_id, **audit)
            result = {'id': str(batch.batch_id), 'accepted': True, 'state': 'pending'}
            await Dao.add(db, HfAuditLog, actor_id=user.user.user_id, actor_kind='user',
                object_type='reconciliation_batch', object_id=str(batch.batch_id), action='create',
                request_id=WriteService.digest({'path': path, 'key': key}), before_after={'after': result}, **audit)
            return await WriteService.finish(db, user, path, key, data, result,
                'reconciliation_batch', batch.batch_id, api_prefix=prefix)
        except BaseException:
            await db.rollback()
            raise
