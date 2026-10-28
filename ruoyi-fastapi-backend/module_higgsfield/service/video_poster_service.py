"""从已授权、已归档的视频提取静态封面，不向浏览器传输整段视频。"""
import asyncio
import os
import subprocess
from collections import OrderedDict
from pathlib import Path

from exceptions.exception import ServiceWarning
from module_higgsfield.service.storage_service import StorageService


class VideoPosterService:
    _cache = OrderedDict()
    _gate = asyncio.Semaphore(2)

    @staticmethod
    def extract(storage, key):
        probe = Path(storage.policy.ffprobe)
        executable = os.environ.get('HF_FFMPEG') or str(probe.with_name('ffmpeg.exe' if os.name == 'nt' else 'ffmpeg'))
        with storage.open_key(key) as source:
            name = str(source.name) if os.name == 'nt' else f'/proc/self/fd/{source.fileno()}'
            extra = {} if os.name == 'nt' else {'pass_fds': (source.fileno(),)}
            try:
                result = subprocess.run([
                    executable, '-v', 'error', '-nostdin', '-protocol_whitelist', 'file,pipe',
                    '-i', name, '-ss', '0', '-frames:v', '1', '-an',
                    '-vf', 'scale=512:512:force_original_aspect_ratio=decrease',
                    '-threads', '1', '-c:v', 'libwebp', '-f', 'image2pipe', 'pipe:1',
                ], capture_output=True, timeout=20, check=True, **extra)
                if not result.stdout or len(result.stdout) > 2 * 1024 * 1024:
                    raise ValueError('封面输出大小无效')
                return result.stdout
            except (OSError, subprocess.SubprocessError, ValueError):
                raise ServiceWarning(message='视频封面暂不可用，请点击预览视频', data={'errorCode': 'VIDEO_POSTER_UNAVAILABLE'}) from None

    @classmethod
    async def stream(cls, key, sha256, head=False, storage=None):
        storage = storage or StorageService()
        cache_key = (storage.policy.root, key, sha256)
        async with cls._gate:
            encoded = cls._cache.get(cache_key)
            if encoded is None:
                encoded = await asyncio.to_thread(cls.extract, storage, key)
                cls._cache[cache_key] = encoded
                while len(cls._cache) > 64:
                    cls._cache.popitem(last=False)
            cls._cache.move_to_end(cache_key)
        async def chunks():
            if not head:
                yield encoded
        return chunks(), {'Content-Length': str(len(encoded)), 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'}, 'image/webp', 200
