"""凭据测试执行器：短事务领取，事务外单次发送并留存加密响应。"""
import asyncio
from exceptions.exception import ServiceWarning
from module_higgsfield.service.credential_test_intent_service import CredentialTestIntentService
from module_higgsfield.service.credential_test_completion_service import CredentialTestCompletionService
from module_higgsfield.service.credential_test_image_probe_service import CredentialTestImageProbeService, UnsupportedCredentialProbe
from module_higgsfield.service.credential_test_response_service import CredentialTestResponseService
from module_higgsfield.service.credential_test_response_crypto_service import CredentialTestResponseCryptoService
from module_higgsfield.service.provider_http_service import ProviderHttpService, HARD_RESPONSE_BYTES


class CredentialTestExecutorService:
    def __init__(self, sessions, storage, evidence_storage, *, max_decoded_bytes, credential_crypto=None,
                 transport_factory=None, procurement_currency=None):
        if type(max_decoded_bytes) is not int or max_decoded_bytes <= 0:
            raise ValueError('测试图片解码容量必须为正整数')
        response_limit = 4 * ((max_decoded_bytes + 2) // 3) + 1_000_000
        if response_limit > HARD_RESPONSE_BYTES or evidence_storage.max_bytes < response_limit:
            raise ValueError('测试响应容量配置不匹配')
        if not isinstance(evidence_storage.crypto, CredentialTestResponseCryptoService):
            raise ValueError('测试响应必须使用专用身份加密域')
        self.sessions, self.storage, self.evidence_storage = sessions, storage, evidence_storage
        self.max_decoded_bytes, self.response_limit = max_decoded_bytes, response_limit
        self.credentials, self.transport_factory = credential_crypto, transport_factory
        self.procurement_currency = procurement_currency

    async def execute(self, test_id):
        transport = None
        def compile_probe(binding):
            nonlocal transport
            payload = CredentialTestImageProbeService.compile(binding)
            transport = (self.transport_factory(binding) if self.transport_factory else
                ProviderHttpService.from_versions(binding.config, binding.version, crypto=self.credentials,
                                                   max_response_bytes=self.response_limit))
            return payload
        try:
            async with self.sessions() as db:
                intent = await CredentialTestIntentService.begin(db, test_id, compile_probe,
                    procurement_currency=self.procurement_currency)
        except UnsupportedCredentialProbe:
            async with self.sessions() as db:
                return await CredentialTestCompletionService.not_sent(db, test_id, 'PROBE_UNSUPPORTED')
        except ServiceWarning as exc:
            code = exc.data.get('errorCode') if isinstance(exc.data, dict) else None
            issue = {'CREDENTIAL_TEST_CONFIG_STALE': 'CONFIG_CHANGED',
                     'CREDENTIAL_TEST_UNAVAILABLE': 'CREDENTIAL_UNAVAILABLE',
                     'RESOURCE_NOT_FOUND': 'CREDENTIAL_UNAVAILABLE',
                     'COST_CENTER_UNAVAILABLE': 'COST_CENTER_UNAVAILABLE',
                     'CREDENTIAL_TEST_MODEL_INVALID': 'MODEL_UNAVAILABLE'}.get(code)
            if issue is None:
                raise
            async with self.sessions() as db:
                return await CredentialTestCompletionService.not_sent(db, test_id, issue)
        if intent is None:
            return False
        # 取消、进程退出或证据落盘失败均保留已提交意图；禁止重新调用 submit。
        response = await transport.submit(intent.payload)
        if response.transport == 'response' and response.body is not None:
            facts = await self.evidence_storage.save(response.body, intent.call_id, test_id)
            async with self.sessions() as db:
                await CredentialTestResponseService.register(db, test_id, intent.call_id, facts,
                                                              http_status=response.http_status)
        result = await asyncio.to_thread(CredentialTestImageProbeService.parse, response,
            max_bytes=self.max_decoded_bytes, verify_media=self.storage.verify_media)
        async with self.sessions() as db:
            return await CredentialTestCompletionService.finish(db, test_id, intent.call_id, result.diagnostic,
                usage_fact=result.image_fact.usage_fact if result.image_fact else None)
