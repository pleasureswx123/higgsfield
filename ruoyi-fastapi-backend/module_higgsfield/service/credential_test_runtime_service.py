"""测试服务心跳和解析代码版本；管理端只读状态，不执行系统命令。"""
import asyncio
import hashlib
import json
from pathlib import Path
from uuid import uuid4
from config.get_redis import RedisUtil


class CredentialTestRuntimeService:
    prefix = 'hf:credential-test:heartbeat:'

    @staticmethod
    def revision():
        root = Path(__file__).parent
        names = ('credential_test_image_probe_service.py', 'image_response_service.py', 'provider_decode_service.py',
                 'credential_video_test_service.py', 'videoplus_response_service.py')
        return hashlib.sha256(b''.join((root / name).read_bytes() for name in names)).hexdigest()

    @classmethod
    async def heartbeat(cls, stop):
        # 在进程启动时固定指纹，不能在旧进程中把新磁盘文件误报为已加载。
        revision, key = cls.revision(), cls.prefix + uuid4().hex
        redis = await RedisUtil.create_redis_pool(log_enabled=False)
        try:
            while not stop.is_set():
                try:
                    await asyncio.wait_for(redis.set(key, json.dumps({'revision': revision}), ex=30), 3)
                except Exception:
                    pass
                try:
                    await asyncio.wait_for(stop.wait(), 5)
                except TimeoutError:
                    pass
        finally:
            await redis.aclose()

    @classmethod
    async def status(cls, redis):
        try:
            revisions = []
            async with asyncio.timeout(3):
                async for key in redis.scan_iter(match=cls.prefix + '*', count=50):
                    value = await redis.get(key)
                    if value:
                        revisions.append(json.loads(value).get('revision'))
                    if len(revisions) >= 100:
                        break
            ready = bool(revisions) and all(value == cls.revision() for value in revisions)
            return {'ready': ready, 'message': '测试服务已就绪' if ready else
                    '测试服务暂未就绪或正在更新，请联系平台维护人员处理；无需操作命令行。'}
        except Exception:
            return {'ready': False, 'message': '暂时无法确认测试服务状态，请稍后刷新或联系平台维护人员。'}
