"""测试工作器启动装配，复用容量、密钥及存储检查。"""
from module_higgsfield.service.image_worker_runtime import image_resources
from module_higgsfield.service.credential_test_response_crypto_service import CredentialTestResponseCryptoService
from module_higgsfield.service.provider_response_storage_service import ProviderResponseStorageService
from module_higgsfield.service.credential_test_executor_service import CredentialTestExecutorService
from module_higgsfield.service.credential_test_worker_service import CredentialTestWorker
from module_higgsfield.service.generation_policy_service import GenerationPolicyService


def create_credential_test_worker(sessions, *, concurrency=4, handler_timeout=300, stale_after_seconds=600):
    storage, credentials, response, maximum = image_resources()
    evidence = ProviderResponseStorageService(storage, CredentialTestResponseCryptoService(credentials.keyring),
                                             max_bytes=response.max_bytes)
    executor = CredentialTestExecutorService(sessions, storage, evidence,
        max_decoded_bytes=maximum, credential_crypto=credentials,
        procurement_currency=GenerationPolicyService.configured().procurement_currency)
    return CredentialTestWorker(executor, concurrency=concurrency, handler_timeout=handler_timeout,
                                stale_after_seconds=stale_after_seconds)
