"""测试受理及发送前共用的绑定校验；调用方负责提交或回滚事务。"""
from dataclasses import dataclass
from module_higgsfield.dao.credential_dao import CredentialDao
from module_higgsfield.dao.credential_test_dao import CredentialTestDao
from module_higgsfield.dao.provider_dao import ProviderDao
from module_higgsfield.dao.model_dao import ModelDao
from module_higgsfield.dao.job_lease_dao import JobLeaseDao
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService


@dataclass(repr=False)
class CredentialTestBinding:
    # 绑定含密文，禁止默认表示输出到日志。
    version: object
    account: object
    config: object
    center: object
    model_version: object | None
    config_hash: str
    model_kind: str | None


class CredentialTestBindingService:
    @staticmethod
    async def require(db, identity, cost_center_id, model_version_id=None, *, expected_hash=None):
        """按统一顺序锁定可变配置；旧测试必须精确匹配受理时摘要。"""
        fail = WorkspaceService.conflict
        model_version = None
        model = None
        version = await CredentialDao.version(db, identity)
        credential = await CredentialDao.get(db, version.credential_id) if version else None
        account = await CredentialDao.account(db, credential.account_id) if credential else None
        if account is None:
            fail('RESOURCE_NOT_FOUND', '凭据版本或账号不存在')
        connection = await ProviderDao.connection(db, account.connection_id, lock=True)
        account = await CredentialDao.account(db, account.account_id, lock=True)
        credential = await CredentialDao.get(db, credential.credential_id, lock=True)
        version = await CredentialDao.version(db, identity, lock=True)
        now = await JobLeaseDao.now(db)
        if (connection is None or connection.status == '2' or account.status != '0'
                or version.state not in {'0', '1'} or version.revoked_time is not None
                or version.valid_from > now or (version.valid_until is not None and version.valid_until <= now)):
            fail('CREDENTIAL_TEST_UNAVAILABLE', '凭据、账号、连接状态或有效期不允许测试')
        config = await ProviderDao.version(db, version.connection_version_id)
        if config is None or config.connection_id != connection.connection_id or connection.current_version_id != config.connection_version_id:
            fail('CREDENTIAL_TEST_CONFIG_STALE', '凭据绑定的连接配置已过期或不匹配，请轮换到当前配置')
        center = await CredentialTestDao.center(db, cost_center_id)
        if center is None or center.active != 'Y':
            fail('COST_CENTER_UNAVAILABLE', '管理成本中心不存在或已停用')
        model_config = None
        if model_version_id:
            model_version = await ModelDao.version(db, model_version_id, lock=True)
            model = await ModelDao.model(db, model_version.model_id) if model_version else None
            if (model is None or model.connection_id != connection.connection_id or model_version.region != account.region
                    or model_version.status == '3'):
                fail('CREDENTIAL_TEST_MODEL_INVALID', '模型版本与连接、区域或状态不一致')
            model_config = {'id': str(model_version.model_version_id), 'revision': str(model_version.revision),
                'alias': model_version.gateway_alias, 'underlying': model_version.underlying_model_id,
                'region': model_version.region, 'capabilities': model_version.capabilities}
        config_hash = WriteService.digest({'schemaVersion': 1, 'credentialVersionId': str(identity),
            'fingerprint': version.fingerprint, 'connectionVersionId': str(config.connection_version_id),
            'connectionHash': config.config_hash, 'accountId': str(account.account_id),
            'region': account.region, 'upstreamProject': account.upstream_project, 'model': model_config})
        if expected_hash is not None and config_hash != expected_hash:
            fail('CREDENTIAL_TEST_CONFIG_STALE', '测试绑定已变化，请重新发起测试')
        return CredentialTestBinding(version, account, config, center, model_version, config_hash, model.kind if model else None)
