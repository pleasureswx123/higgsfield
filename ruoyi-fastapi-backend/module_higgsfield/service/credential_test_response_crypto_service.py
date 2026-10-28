"""复用响应加密封装，身份域与生成任务严格隔离。"""
from module_higgsfield.service.provider_response_crypto_service import ProviderResponseCryptoService, MAX_ID


class CredentialTestResponseCryptoService(ProviderResponseCryptoService):
    @staticmethod
    def context(call_id: int, test_id: int) -> bytes:
        if any(type(value) is not int or not 0 < value <= MAX_ID for value in (call_id, test_id)):
            raise ValueError('测试响应证据绑定身份无效')
        return f'hf:credential-test-response:v1:{call_id}:{test_id}'.encode()
