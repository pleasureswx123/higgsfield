"""测试候选只返回同连接区域的非秘密模型信息，不表示探针已通过。"""
from common.vo import PageModel
from module_higgsfield.dao.credential_dao import CredentialDao
from module_higgsfield.dao.provider_dao import ProviderDao
from module_higgsfield.dao.job_lease_dao import JobLeaseDao
from module_higgsfield.dao.credential_test_model_dao import CredentialTestModelDao
from module_higgsfield.service.admin_scope_service import AdminScopeService
from module_higgsfield.service.project_workspace_service import WorkspaceService


class CredentialTestModelService:
    @staticmethod
    async def listing(db, user, identity, query):
        await AdminScopeService.global_access(db, user, 'credential:test')
        version = await CredentialDao.version(db, identity)
        credential = await CredentialDao.get(db, version.credential_id) if version else None
        account = await CredentialDao.account(db, credential.account_id) if credential else None
        if account is None:
            WorkspaceService.conflict('RESOURCE_NOT_FOUND', '凭据版本不存在')
        now = await JobLeaseDao.now(db)
        connection = await ProviderDao.connection(db, account.connection_id)
        config = await ProviderDao.version(db, version.connection_version_id)
        if (version.state not in {'0', '1'} or version.revoked_time is not None or version.valid_from > now
                or (version.valid_until is not None and version.valid_until <= now) or account.status != '0'
                or connection is None or connection.status == '2' or config is None
                or connection.current_version_id != version.connection_version_id
                or config.connection_id != account.connection_id or config.adapter_version != 'videoplus-v1'):
            WorkspaceService.conflict('CREDENTIAL_TEST_UNAVAILABLE', '当前凭据或连接不满足图片测试条件')
        rows, total = await CredentialTestModelDao.page(db, account.connection_id, account.region, query)
        return PageModel(rows=[dict(id=str(row.model_version_id), name=row.display_name,
            versionNo=row.version_no, gatewayAlias=row.gateway_alias,
            status={'0': 'draft', '1': 'verified', '2': 'published'}[row.status]) for row in rows],
            total=total, pageNum=query.page_num, pageSize=query.page_size,
            hasNext=query.page_num * query.page_size < total)
