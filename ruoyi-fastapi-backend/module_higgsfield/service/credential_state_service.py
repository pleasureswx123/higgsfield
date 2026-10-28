"""本地凭据排空、停用和撤销；不会替换任务原始 Key 或声称上游停止收费。"""

from module_higgsfield.dao.credential_dao import CredentialDao
from module_higgsfield.dao.provider_dao import ProviderDao
from module_higgsfield.dao.price_source_dao import PriceSourceDao
from module_higgsfield.service.admin_scope_service import AdminScopeService
from module_higgsfield.service.credential_service import CredentialService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService


class CredentialStateService:
    @classmethod
    async def mutate(cls, db, user, identity, action, payload, key):
        if action not in ('drain', 'disable', 'revoke'):
            raise ValueError('不支持的凭据状态操作')
        path, prefix = f'/credential-versions/{identity}/{action}', '/api/admin/v1'
        permission = 'credential:revoke' if action == 'revoke' else 'credential:disable'
        data = payload.model_dump(by_alias=True)
        fail = WorkspaceService.conflict
        try:
            await AdminScopeService.global_access(db, user, permission)
            await WriteService.lock(db, user, path, key, api_prefix=prefix)
            replay = await WriteService.replay(db, user, path, key, data, api_prefix=prefix)
            if replay:
                await db.commit()
                return replay, True
            version = await CredentialDao.version(db, identity)
            credential = await CredentialDao.get(db, version.credential_id) if version else None
            account = await CredentialDao.account(db, credential.account_id) if credential else None
            if account is None:
                fail('CREDENTIAL_VERSION_NOT_FOUND', '凭据版本或所属账号不存在')
            connection = await ProviderDao.connection(db, account.connection_id, lock=True)
            if connection is None:
                fail('CREDENTIAL_CONNECTION_NOT_FOUND', '凭据所属连接不存在')
            await CredentialDao.account(db, account.account_id, lock=True)
            credential = await CredentialDao.get(db, credential.credential_id, lock=True)
            version = await CredentialDao.version(db, identity, lock=True)
            WorkspaceService.check_revision(version, payload.revision)
            allowed = {'drain': {'1'}, 'disable': {'0', '2'}, 'revoke': {'0', '1', '2', '3'}}
            if version.state not in allowed[action]:
                fail('CREDENTIAL_STATE_CONFLICT', '当前状态不允许此操作；启用版本须先排空再停用')
            count = (await CredentialDao.in_flight(db, [version.credential_version_id])).get(
                version.credential_version_id, 0
            )
            if action == 'disable' and count:
                fail('CREDENTIAL_IN_FLIGHT', '仍有任务依赖原凭据，排空完成前不能停用')
            before = CredentialService.version_result(version, count)
            # 审计采用 JSON 安全投影，不包含加密字段和完整指纹。
            before = {
                name: value.isoformat() if hasattr(value, 'isoformat') else value for name, value in before.items()
            }
            audit = WriteService.audit(user)
            version.state = {'drain': '2', 'disable': '3', 'revoke': '4'}[action]
            version.revision += 1
            version.update_by, version.update_time = audit['update_by'], audit['update_time']
            if action == 'revoke':
                version.revoked_time = audit['update_time']
            states = set(await CredentialDao.version_states(db, credential.credential_id))
            credential.status = next(state for state in ('1', '2', '0', '3', '4') if state in states)
            credential.revision += 1
            credential.update_by, credential.update_time = audit['update_by'], audit['update_time']
            after = CredentialService.version_result(version, count)
            safe_after = {
                name: value.isoformat() if hasattr(value, 'isoformat') else value for name, value in after.items()
            }
            await PriceSourceDao.audit(
                db,
                dict(
                    actor_id=user.user.user_id,
                    actor_kind='user',
                    object_type='credential_version',
                    object_id=str(version.credential_version_id),
                    action=action,
                    reason=payload.reason,
                    request_id=WriteService.digest({'path': path, 'key': key}),
                    before_after={
                        'before': before,
                        'after': safe_after,
                        'credentialStatus': CredentialService.states[credential.status],
                    },
                    **audit,
                ),
            )
            return await WriteService.finish(
                db, user, path, key, data, after, 'credential_version', version.credential_version_id, api_prefix=prefix
            )
        except Exception:
            await db.rollback()
            raise
