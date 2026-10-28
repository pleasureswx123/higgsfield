"""归档工作器启动装配；下载出口与存储位置必须显式配置。"""

import json
import os

from module_higgsfield.service.output_archive_worker import OutputArchiveWorker
from module_higgsfield.service.output_download_service import OutputDownloadPolicy, OutputDownloadService
from module_higgsfield.service.output_source_crypto_service import OutputSourceCryptoService
from module_higgsfield.service.storage_service import StoragePolicy, StorageService


def create_archive_worker(sessions, worker, *, batch_size=4, lease_seconds=60):
    try:
        config = json.loads(os.environ['HF_OUTPUT_DOWNLOAD_POLICY'])
        if not isinstance(config, dict) or set(config) - {'allowed_hosts', 'max_bytes', 'timeout_seconds'}:
            raise ValueError
        hosts = config['allowed_hosts']
        if (
            not isinstance(hosts, list)
            or not hosts
            or any(
                not isinstance(host, str) or not host or host != host.lower() or any(c in host for c in '/:@* ')
                for host in hosts
            )
        ):
            raise ValueError
        policy = OutputDownloadPolicy(
            tuple(hosts), config['max_bytes'], timeout_seconds=config.get('timeout_seconds', 120)
        )
    except (KeyError, TypeError, ValueError):
        raise ValueError('HF_OUTPUT_DOWNLOAD_POLICY必须提供精确主机白名单和正整数字节上限') from None
    storage = StorageService(StoragePolicy.from_environment())
    storage.verify_root()
    return OutputArchiveWorker(
        sessions,
        worker,
        OutputDownloadService(storage, policy),
        OutputSourceCryptoService(),
        batch_size=batch_size,
        lease_seconds=lease_seconds,
    )
