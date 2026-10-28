"""凭据启用必须引用当前配置的完整成功测试，不能替换历史任务绑定。"""
from module_higgsfield.dao.credential_dao import CredentialDao
from module_higgsfield.dao.credential_test_dao import CredentialTestDao
from module_higgsfield.dao.credential_test_response_dao import CredentialTestResponseDao
from module_higgsfield.dao.provider_call_dao import ProviderCallDao
from module_higgsfield.dao.price_source_dao import PriceSourceDao
from module_higgsfield.entity.vo.credential_test_result_vo import CredentialTestResult
from module_higgsfield.service.admin_scope_service import AdminScopeService
from module_higgsfield.service.credential_test_binding_service import CredentialTestBindingService
from module_higgsfield.service.credential_service import CredentialService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService


class CredentialActivationService:
    @staticmethod
    async def activate(db, user, identity, payload, key):
        path, prefix = f'/credential-versions/{identity}/activate', '/api/admin/v1'
        data = payload.model_dump(by_alias=True)
        fail = WorkspaceService.conflict
        try:
            await AdminScopeService.global_access(db, user, 'credential:activate')
            await WriteService.lock(db, user, path, key, api_prefix=prefix)
            replay = await WriteService.replay(db, user, path, key, data, api_prefix=prefix)
            if replay:
                await db.commit()
                return replay, True
            test = await CredentialTestDao.locked(db, int(payload.test_id))
            if (test is None or test.credential_version_id != identity or test.state != '1'
                    or test.finished_time is None or test.provider_call_id is None
                    or test.config_hash != payload.expected_config_hash or test.model_version_id is None):
                fail('CREDENTIAL_TEST_INVALID', '缺少与本凭据和预期配置匹配的成功测试')
            try:
                diagnostic = CredentialTestResult.model_validate(test.result)
            except ValueError:
                fail('CREDENTIAL_TEST_INVALID', '测试诊断证据无效')
            if not diagnostic.model_verified:
                fail('CREDENTIAL_TEST_INVALID', '测试尚未证明模型调用通过')
            binding = await CredentialTestBindingService.require(db, identity, test.cost_center_id,
                test.model_version_id, expected_hash=payload.expected_config_hash)
            version = binding.version
            WorkspaceService.check_revision(version, payload.revision)
            if version.state != '0':
                fail('CREDENTIAL_STATE_CONFLICT', '只有通过测试的草稿版本可以启用')
            call = await ProviderCallDao.locked(db, test.provider_call_id)
            evidence = await CredentialTestResponseDao.get(db, test.test_id)
            if (call is None or call.state != '2' or call.operation != 'test' or call.acceptance != 'accepted'
                    or call.credential_version_id != identity or call.cost_center_id != test.cost_center_id
                    or call.account_id != binding.account.account_id
                    or call.request_metadata.get('testId') != str(test.test_id)
                    or call.request_metadata.get('configHash') != test.config_hash
                    or call.response_metadata != test.result
                    or evidence is None or evidence.provider_call_id != call.call_id
                    or evidence.http_status != diagnostic.http_status or call.http_status != diagnostic.http_status):
                fail('CREDENTIAL_TEST_INVALID', '测试调用和原始响应证据不完整或不匹配')
            credential = await CredentialDao.get(db, version.credential_id)
            audit = WriteService.audit(user)
            before = {'state': 'draft', 'revision': str(version.revision)}
            version.state = '1'
            version.revision += 1
            version.update_by, version.update_time = audit['update_by'], audit['update_time']
            credential.status = '1'
            credential.revision += 1
            credential.update_by, credential.update_time = audit['update_by'], audit['update_time']
            result = CredentialService.version_result(version, 0)
            await PriceSourceDao.audit(db, dict(actor_id=user.user.user_id, actor_kind='user',
                object_type='credential_version', object_id=str(identity), action='activate', reason=payload.reason,
                request_id=WriteService.digest({'path': path, 'key': key}),
                before_after={'before': before, 'after': {'state': 'active', 'revision': str(version.revision)},
                              'testId': str(test.test_id), 'configHash': test.config_hash}, **audit))
            return await WriteService.finish(db, user, path, key, data, result, 'credential_version', identity, api_prefix=prefix)
        except Exception:
            await db.rollback()
            raise
