"""图片生成及证据恢复工作器装配，容量、密钥和存储在启动时校验。"""

import os

from module_higgsfield.service.credential_crypto_service import CredentialCryptoService
from module_higgsfield.service.generation_worker_service import GenerationWorkerService
from module_higgsfield.service.image_archive_recovery_worker import ImageArchiveRecoveryWorker
from module_higgsfield.service.image_storage_service import ImageStorageService
from module_higgsfield.service.image_submit_handler import ImageSubmitHandler
from module_higgsfield.service.image_reconciliation_handler import ImageReconciliationHandler
from module_higgsfield.service.provider_http_service import HARD_RESPONSE_BYTES
from module_higgsfield.service.provider_response_crypto_service import ProviderResponseCryptoService
from module_higgsfield.service.provider_response_storage_service import ProviderResponseStorageService
from module_higgsfield.service.storage_service import StorageService
from module_higgsfield.service.videoplus_media_resolver import VideoPlusMediaResolver


def image_resources(*, storage=None, credential_crypto=None, max_decoded_bytes=None):
    if max_decoded_bytes is None:
        raw = os.environ.get('HF_IMAGE_MAX_DECODED_BYTES', '')
        if not raw.isascii() or not raw.isdigit():
            raise ValueError('必须配置HF_IMAGE_MAX_DECODED_BYTES为正整数字节数')
        max_decoded_bytes = int(raw)
    if type(max_decoded_bytes) is not int or max_decoded_bytes <= 0:
        raise ValueError('图片解码容量必须为正整数')
    response_limit = 4 * ((max_decoded_bytes + 2) // 3) + 1_000_000
    if response_limit > HARD_RESPONSE_BYTES:
        raise ValueError('图片响应容量超过传输硬上限')
    storage = storage or StorageService()
    storage.verify_root()
    credentials = credential_crypto or CredentialCryptoService()
    evidence = ProviderResponseStorageService(
        storage,
        ProviderResponseCryptoService(credentials.keyring),
        max_bytes=response_limit,
    )
    return storage, credentials, evidence, max_decoded_bytes


def create_image_worker(
    sessions,
    worker_id,
    *,
    concurrency=4,
    lease_seconds=60,
    handler_timeout=300,
    storage=None,
    credential_crypto=None,
    max_decoded_bytes=None,
):
    storage, credentials, evidence, maximum = image_resources(
        storage=storage,
        credential_crypto=credential_crypto,
        max_decoded_bytes=max_decoded_bytes,
    )
    return GenerationWorkerService(
        sessions,
        worker_id,
        {
            'prepare': ImageSubmitHandler(
                ImageStorageService(storage),
                evidence_storage=evidence,
                max_decoded_bytes=maximum,
                credential_crypto=credentials,
                media_resolver=VideoPlusMediaResolver(credential_crypto=credentials, storage=storage),
            ),
            'reconcile_submission': ImageReconciliationHandler(
                evidence, ImageStorageService(storage), max_decoded_bytes=maximum
            ),
        },
        concurrency=concurrency,
        lease_seconds=lease_seconds,
        handler_timeout=handler_timeout,
        kinds=('image',),
    )


def create_image_recovery_worker(
    sessions, worker_id, *, batch_size=4, lease_seconds=60, storage=None, credential_crypto=None, max_decoded_bytes=None
):
    storage, _, evidence, maximum = image_resources(
        storage=storage,
        credential_crypto=credential_crypto,
        max_decoded_bytes=max_decoded_bytes,
    )
    return ImageArchiveRecoveryWorker(
        sessions,
        worker_id,
        evidence,
        ImageStorageService(storage),
        max_decoded_bytes=maximum,
        batch_size=batch_size,
        lease_seconds=lease_seconds,
    )
