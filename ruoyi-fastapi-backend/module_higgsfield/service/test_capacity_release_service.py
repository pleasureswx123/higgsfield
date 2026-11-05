"""管理员确认供应商已停止后释放未知测试的本地名额，保留原测试和费用事实。"""
from module_higgsfield.dao.credential_test_dao import CredentialTestDao
from module_higgsfield.dao.provider_call_dao import ProviderCallDao
from module_higgsfield.dao.job_lease_dao import JobLeaseDao
from module_higgsfield.dao.price_source_dao import PriceSourceDao
from module_higgsfield.service.admin_scope_service import AdminScopeService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService


class TestCapacityReleaseService:
    @staticmethod
    async def release(db, user, identity, payload, key):
        path, prefix = f'/credential-tests/{identity}/release-capacity', '/api/admin/v1'
        data = payload.model_dump(by_alias=True)
        try:
            await AdminScopeService.global_access(db, user, 'credential:test')
            await WriteService.lock(db, user, path, key, api_prefix=prefix)
            row = await CredentialTestDao.locked(db, identity)
            if row is None:
                WorkspaceService.conflict('RESOURCE_NOT_FOUND', '测试记录不存在')
            replay = await WriteService.replay(db, user, path, key, data, api_prefix=prefix)
            if replay:
                await db.commit()
                return replay, True
            call = await ProviderCallDao.locked(db, row.provider_call_id) if row.provider_call_id else None
            if row.state == '0' or call is None or call.acceptance != 'unknown':
                WorkspaceService.conflict('TEST_CAPACITY_RELEASE_UNAVAILABLE', '仅可核查并释放已停止执行且结果未知的测试名额')
            now = await JobLeaseDao.now(db)
            if not call.request_metadata.get('capacityReleasedAt'):
                call.request_metadata = {**call.request_metadata, 'capacityReleasedAt': now.isoformat(),
                                         'capacityReleaseEvidence': payload.evidence_ref}
                call.update_by, call.update_time = user.user.user_name, now
                await PriceSourceDao.audit(db, dict(actor_id=user.user.user_id, actor_kind='user',
                    object_type='credential_test', object_id=str(identity), action='release_test_capacity',
                    reason=payload.reason, request_id=WriteService.digest({'path': path, 'key': key}),
                    before_after={'capacityReleased': True, 'evidenceRef': payload.evidence_ref},
                    **WriteService.audit(user)))
            return await WriteService.finish(db, user, path, key, data,
                {'testId': str(identity), 'capacityReleased': True}, 'credential_test', identity, api_prefix=prefix)
        except Exception:
            await db.rollback()
            raise
