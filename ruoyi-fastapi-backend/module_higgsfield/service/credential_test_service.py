"""测试受理只保存待执行事实，不解密秘密或发起供应商消费。"""
from module_higgsfield.dao.credential_test_dao import CredentialTestDao
from module_higgsfield.dao.price_source_dao import PriceSourceDao
from module_higgsfield.service.credential_test_binding_service import CredentialTestBindingService
from module_higgsfield.service.admin_scope_service import AdminScopeService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService
from module_higgsfield.entity.vo.credential_test_result_vo import CredentialTestResult
from module_higgsfield.dao.credential_dao import CredentialDao
from common.vo import PageModel
from module_higgsfield.service.credential_test_cost_service import CredentialTestCostService


class CredentialTestService:
    @classmethod
    async def listing(cls, db, user, version_id, query):
        await AdminScopeService.global_access(db, user, 'credential:read')
        if await CredentialDao.version(db, version_id) is None:
            WorkspaceService.conflict('RESOURCE_NOT_FOUND', '凭据版本不存在')
        rows, total = await CredentialTestDao.page(db, version_id, query)
        records = await CredentialTestCostService.attach(db, user, [cls.result(row) for row in rows])
        return PageModel(rows=records, total=total, pageNum=query.page_num,
            pageSize=query.page_size, hasNext=query.page_num * query.page_size < total)

    @staticmethod
    def result(row):
        # 仅按固定诊断契约投影；历史异常载荷不整体透传。
        diagnostic = {}
        if row.state != '0':
            try:
                diagnostic = CredentialTestResult.model_validate(row.result).model_dump(by_alias=True)
            except ValueError:
                diagnostic = {'issue': 'RESPONSE_INVALID'}
        return {'id': str(row.test_id), 'credentialVersionId': str(row.credential_version_id),
                'connectionVersionId': str(row.connection_version_id), 'configHash': row.config_hash,
                'modelVersionId': str(row.model_version_id) if row.model_version_id else None,
                'costCenterId': str(row.cost_center_id), 'requestedBy': str(row.requested_by),
                'state': ('pending', 'passed', 'failed')[int(row.state)],
                'providerCallId': str(row.provider_call_id) if row.provider_call_id else None,
                'finishedAt': row.finished_time.isoformat() if row.finished_time else None,
                'createTime': row.create_time.isoformat(), 'result': diagnostic}

    @classmethod
    async def get(cls, db, user, identity):
        await AdminScopeService.global_access(db, user, 'credential:read')
        row = await CredentialTestDao.get(db, identity)
        if row is None:
            WorkspaceService.conflict('RESOURCE_NOT_FOUND', '测试记录不存在')
        return (await CredentialTestCostService.attach(db, user, [cls.result(row)]))[0]

    @classmethod
    async def create(cls, db, user, identity, payload, key):
        path, prefix = f'/credential-versions/{identity}/tests', '/api/admin/v1'
        data = payload.model_dump(by_alias=True)
        try:
            await AdminScopeService.global_access(db, user, 'credential:test')
            await WriteService.lock(db, user, path, key, api_prefix=prefix)
            replay = await WriteService.replay(db, user, path, key, data, api_prefix=prefix)
            if replay:
                await db.commit()
                return replay, True
            binding = await CredentialTestBindingService.require(db, identity, int(payload.cost_center_id),
                int(payload.model_version_id) if payload.model_version_id else None)
            config, center, config_hash = binding.config, binding.center, binding.config_hash
            audit = WriteService.audit(user)
            row = await CredentialTestDao.add(db, dict(credential_version_id=identity,
                connection_version_id=config.connection_version_id, config_hash=config_hash,
                model_version_id=int(payload.model_version_id) if payload.model_version_id else None,
                cost_center_id=center.cost_center_id, requested_by=user.user.user_id, state='0', result={}, **audit))
            receipt = {'id': str(row.test_id), 'accepted': True, 'state': 'pending'}
            await PriceSourceDao.audit(db, dict(actor_id=user.user.user_id, actor_kind='user',
                object_type='credential_test', object_id=str(row.test_id), action='request_test',
                request_id=WriteService.digest({'path': path, 'key': key}),
                before_after={'after': cls.result(row), 'acknowledgePotentialCharge': True}, **audit))
            return await WriteService.finish(db, user, path, key, data, receipt, 'credential_test', row.test_id, api_prefix=prefix)
        except Exception:
            await db.rollback()
            raise
