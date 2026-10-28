"""测试执行事实原子回收；结束记录不被迟到响应覆盖。"""
from module_higgsfield.dao.credential_test_dao import CredentialTestDao
from module_higgsfield.dao.provider_call_dao import ProviderCallDao
from module_higgsfield.dao.job_lease_dao import JobLeaseDao
from module_higgsfield.dao.credential_test_response_dao import CredentialTestResponseDao
from module_higgsfield.entity.vo.credential_test_result_vo import CredentialTestResult
from module_higgsfield.service.credential_test_usage_service import CredentialTestUsageService
from module_higgsfield.service.credential_test_billing_service import CredentialTestBillingService


class CredentialTestCompletionService:
    @staticmethod
    def diagnostic(value):
        # 即便传入模型也重新校验，避免 model_construct 或事后赋值绕过约束。
        return CredentialTestResult.model_validate(value.model_dump() if isinstance(value, CredentialTestResult) else value)

    @classmethod
    async def finish(cls, db, test_id, call_id, result, *, usage_fact=None):
        """仅供内部执行器提交事实；不会发起网络请求或启用凭据。"""
        try:
            result = cls.diagnostic(result)
            if result.transport == 'not_sent':
                raise ValueError('调用意图已经提交，不能回写为未发送')
            row = await CredentialTestDao.locked(db, test_id)
            if row is None or row.state != '0':
                await db.commit()
                return False
            if row.provider_call_id != call_id:
                raise ValueError('测试与调用身份不匹配')
            if result.model_verified and row.model_version_id is None:
                raise ValueError('未绑定模型版本的测试不能证明模型通过')
            if result.model_verified:
                evidence = await CredentialTestResponseDao.get(db, test_id)
                if evidence is None or evidence.provider_call_id != call_id or evidence.http_status != result.http_status:
                    raise ValueError('模型通过必须保留本次调用的响应证据')
            call = await ProviderCallDao.locked(db, call_id)
            if (call is None or call.operation != 'test' or call.state != '1'
                    or call.cost_center_id != row.cost_center_id or call.job_id is not None
                    or call.credential_version_id != row.credential_version_id
                    or call.actor_id != row.requested_by
                    or call.request_metadata.get('testId') != str(row.test_id)
                    or call.request_metadata.get('configHash') != row.config_hash):
                raise ValueError('测试调用绑定或运行状态不一致')
            now = await JobLeaseDao.now(db)
            if usage_fact is not None:
                evidence = await CredentialTestResponseDao.get(db, test_id)
                if result.transport != 'response' or evidence is None or evidence.provider_call_id != call_id:
                    raise ValueError('测试用量必须来自已留存的响应')
            await CredentialTestUsageService.append(db, row, call, usage_fact, now=now)
            await CredentialTestBillingService.calculate(db, row, call, now=now)
            diagnostic = result.model_dump(by_alias=True)
            call.state = '2' if result.transport == 'response' else '3'
            call.acceptance = result.acceptance
            call.http_status = result.http_status
            call.response_metadata = diagnostic
            call.finished_time = now
            call.update_time = now
            call.update_by = 'credential-test-worker'
            row.state = '1' if result.model_verified else '2'
            row.result = diagnostic
            row.finished_time = now
            row.update_time = now
            row.update_by = 'credential-test-worker'
            await db.commit()
            return True
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def not_sent(cls, db, test_id, issue):
        """准备失败仅结束尚无调用意图的测试，不能抹去可能已消费的事实。"""
        try:
            if issue not in {'CONFIG_CHANGED', 'CREDENTIAL_UNAVAILABLE', 'COST_CENTER_UNAVAILABLE',
                             'MODEL_UNAVAILABLE', 'PROBE_UNSUPPORTED'}:
                raise ValueError('未发送测试必须使用固定准备失败原因')
            result = CredentialTestResult(transport='not_sent', authentication='unknown',
                acceptance='not_applicable', issue=issue)
            row = await CredentialTestDao.locked(db, test_id)
            if row is None or row.state != '0' or row.provider_call_id is not None:
                await db.commit()
                return False
            now = await JobLeaseDao.now(db)
            row.state = '2'
            row.result = result.model_dump(by_alias=True)
            row.finished_time = now
            row.update_time = now
            row.update_by = 'credential-test-worker'
            await db.commit()
            return True
        except Exception:
            await db.rollback()
            raise
