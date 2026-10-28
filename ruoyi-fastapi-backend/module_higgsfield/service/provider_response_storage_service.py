"""有界供应商响应证据文件，提供加密持久化及完整性验证读取。"""

import asyncio
import hashlib
import json
import os
import re
from uuid import uuid4

from module_higgsfield.service.provider_http_service import HARD_RESPONSE_BYTES, invalid_constant
from module_higgsfield.service.provider_response_crypto_service import ProviderResponseCryptoService
from module_higgsfield.service.storage_service import StorageService
from module_higgsfield.service.videoplus_response_service import unique_object

ENVELOPE_OVERHEAD = 512


class ProviderResponseStorageService:
    def __init__(self, storage: StorageService, crypto: ProviderResponseCryptoService, *, max_bytes: int) -> None:
        if type(max_bytes) is not int or not 0 < max_bytes <= HARD_RESPONSE_BYTES:
            raise ValueError('响应证据容量上限无效')
        self.storage, self.crypto, self.max_bytes = storage, crypto, max_bytes

    def _save(self, body: object, call_id: int, job_id: int) -> dict:
        # 仅保存完整解析后的JSON值；不记录Authorization或供应商Key。
        raw = json.dumps(body, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
        if len(raw) > self.max_bytes:
            raise ValueError('响应证据超过容量上限')
        encrypted = self.crypto.encrypt(raw, call_id, job_id)
        key = 'provider-evidence/' + uuid4().hex
        created = False
        try:
            with self.storage.open_key(key, write=True) as handle:
                created = True
                handle.write(encrypted)
                handle.flush()
                os.fsync(handle.fileno())
            return {'storage_key': key, 'sha256': hashlib.sha256(encrypted).hexdigest(), 'byte_size': len(encrypted)}
        except BaseException:
            if created:
                try:
                    self.storage.remove_unbound_key(key)
                except Exception:
                    pass
            raise

    async def save(self, body: object, call_id: int, job_id: int) -> dict:
        task = asyncio.create_task(asyncio.to_thread(self._save, body, call_id, job_id))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # 文件已完整保存但尚未登记时保留证据，不删除可能是唯一副本的响应。
            await asyncio.gather(task, return_exceptions=True)
            raise

    def _load(self, facts: dict, call_id: int, job_id: int) -> object:
        key, expected, size = facts['storage_key'], facts['sha256'], facts['byte_size']
        if (
            not isinstance(key, str)
            or not re.fullmatch(r'provider-evidence/[a-f0-9]{32}', key)
            or not isinstance(expected, str)
            or not re.fullmatch(r'[a-f0-9]{64}', expected)
            or type(size) is not int
            or not 0 < size <= self.max_bytes + ENVELOPE_OVERHEAD
        ):
            raise ValueError('响应证据文件事实无效')
        with self.storage.open_key(key) as handle:
            data = handle.read(size + 1)
        if len(data) != size or hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('响应证据文件大小或摘要不一致')
        raw = self.crypto.decrypt(data, call_id, job_id)
        if len(raw) > self.max_bytes:
            raise ValueError('响应证据解密后超过容量上限')
        return json.loads(raw, object_pairs_hook=unique_object, parse_constant=invalid_constant)

    async def load(self, facts: dict, call_id: int, job_id: int) -> object:
        return await asyncio.to_thread(self._load, facts, call_id, job_id)
