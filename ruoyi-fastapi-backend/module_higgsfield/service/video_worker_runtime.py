"""注册视频提交、响应证据恢复与轮询处理器，不占用其他任务类型。"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from module_higgsfield.service.credential_crypto_service import CredentialCryptoService
from module_higgsfield.service.generation_worker_service import GenerationWorkerService
from module_higgsfield.service.output_source_crypto_service import OutputSourceCryptoService
from module_higgsfield.service.videoplus_media_resolver import VideoPlusMediaResolver
from module_higgsfield.service.videoplus_poll_handler import VideoPlusPollHandler
from module_higgsfield.service.videoplus_submit_handler import VideoPlusSubmitHandler
from module_higgsfield.service.video_reconciliation_handler import VideoReconciliationHandler
from module_higgsfield.service.provider_http_service import MAX_RESPONSE_BYTES
from module_higgsfield.service.provider_response_crypto_service import ProviderResponseCryptoService
from module_higgsfield.service.provider_response_storage_service import ProviderResponseStorageService
from module_higgsfield.service.storage_service import StorageService


def create_video_worker(
    sessions: async_sessionmaker[AsyncSession],
    worker_id: str,
    *,
    concurrency: int = 4,
    lease_seconds: int = 60,
    handler_timeout: float = 300,
    credential_crypto: CredentialCryptoService | None = None,
    output_crypto: OutputSourceCryptoService | None = None,
    storage: StorageService | None = None,
) -> GenerationWorkerService:
    credentials = credential_crypto or CredentialCryptoService()
    outputs = output_crypto or OutputSourceCryptoService()
    storage = storage or StorageService()
    storage.verify_root()
    evidence = ProviderResponseStorageService(
        storage, ProviderResponseCryptoService(credentials.keyring), max_bytes=MAX_RESPONSE_BYTES
    )
    return GenerationWorkerService(
        sessions,
        worker_id,
        {
            'prepare': VideoPlusSubmitHandler(
                credential_crypto=credentials,
                media_resolver=VideoPlusMediaResolver(credential_crypto=credentials, storage=storage),
                evidence_storage=evidence,
            ),
            'reconcile_submission': VideoReconciliationHandler(evidence),
            'poll': VideoPlusPollHandler(credential_crypto=credentials, output_crypto=outputs),
        },
        concurrency=concurrency,
        lease_seconds=lease_seconds,
        handler_timeout=handler_timeout,
        kinds=('video',),
    )
