"""按超时窗口回收已登记意图；只读取证据，绝不重新发送。"""
import asyncio
from datetime import timedelta
from module_higgsfield.dao.credential_test_dao import CredentialTestDao
from module_higgsfield.dao.credential_test_response_dao import CredentialTestResponseDao
from module_higgsfield.dao.provider_call_dao import ProviderCallDao
from module_higgsfield.dao.job_lease_dao import JobLeaseDao
from module_higgsfield.service.credential_test_completion_service import CredentialTestCompletionService
from module_higgsfield.service.credential_test_image_probe_service import CredentialTestImageProbeService
from module_higgsfield.service.provider_http_service import ProviderHttpResult


class CredentialTestRecoveryService:
    def __init__(self, executor, *, stale_after_seconds):
        if type(stale_after_seconds) is not int or stale_after_seconds < 60:
            raise ValueError('测试回收窗口至少为60秒，并应覆盖部署的请求与落盘最长耗时')
        self.executor = executor
        self.stale_after_seconds = stale_after_seconds

    async def recover(self, test_id):
        async with self.executor.sessions() as db:
            test = await CredentialTestDao.locked(db, test_id)
            if test is None or test.state != '0' or test.provider_call_id is None:
                return False
            call = await ProviderCallDao.locked(db, test.provider_call_id)
            now = await JobLeaseDao.now(db)
            if (call is None or call.state != '1' or call.started_time is None
                    or call.started_time > now - timedelta(seconds=self.stale_after_seconds)):
                return False
            call_id = call.call_id
            evidence = await CredentialTestResponseDao.get(db, test_id)
            if evidence is None:
                # 保持测试行锁到提交，防止把同期刚登记的响应误记为无响应。
                return await CredentialTestCompletionService.finish(db, test_id, call_id,
                    dict(transport='network_error', authentication='unknown', acceptance='unknown',
                         issue='EXECUTION_INTERRUPTED'))
            if evidence.provider_call_id != call_id:
                raise ValueError('测试响应索引与调用身份不匹配')
            facts = {key: getattr(evidence, key) for key in ('storage_key', 'sha256', 'byte_size')}
            http_status = evidence.http_status
        # 密文读取、认证和图片解码均在事务外；文件暂不可用时保持待回收，不伪造诊断。
        body = await self.executor.evidence_storage.load(facts, call_id, test_id)
        result = await asyncio.to_thread(CredentialTestImageProbeService.parse,
            ProviderHttpResult(transport='response', http_status=http_status, body=body),
            max_bytes=self.executor.max_decoded_bytes, verify_media=self.executor.storage.verify_media)
        async with self.executor.sessions() as db:
            return await CredentialTestCompletionService.finish(db, test_id, call_id, result.diagnostic,
                usage_fact=result.image_fact.usage_fact if result.image_fact else None)
