"""真实本地Redis验证传输防重放原子性，仅使用随机测试键。"""
import asyncio
import os
import unittest
from uuid import uuid4
from unittest.mock import patch

from fastapi import FastAPI, Request
from redis.asyncio import Redis

from config.env import RedisConfig, TransportCryptoConfig
from utils.transport_crypto_util import TransportSecurityUtil


@unittest.skipUnless(os.getenv('HF_RUN_REDIS_TESTS') == '1', '需显式启用本地Redis测试')
class TransportReplayRedisTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertIn(RedisConfig.redis_host, ('127.0.0.1', 'localhost', '::1'), '仅允许本地Redis')
        self.redis = Redis(host=RedisConfig.redis_host, port=RedisConfig.redis_port,
                           username=RedisConfig.redis_username, password=RedisConfig.redis_password,
                           db=RedisConfig.redis_database, decode_responses=True,
                           socket_connect_timeout=2, socket_timeout=2)
        self.keys = []
        self.addAsyncCleanup(self.cleanup)
        await self.redis.ping()
        app = FastAPI()
        app.state.redis = self.redis
        self.request = Request({'type': 'http', 'method': 'POST', 'path': '/login',
                                'headers': [], 'app': app})
        self.kid = f'hf-test-{uuid4().hex}'

    async def cleanup(self):
        if self.keys:
            await self.redis.delete(*self.keys)
            self.assertEqual(await self.redis.exists(*self.keys), 0)
        await self.redis.aclose()

    def nonce(self):
        value = uuid4().hex
        self.keys.append(f'transport:replay:{self.kid}:{value}')
        return value

    async def test_same_nonce_concurrent_requests_have_one_winner_and_expiry(self):
        nonce = self.nonce()
        with patch.object(TransportCryptoConfig, 'transport_crypto_mode', 'required'):
            results = await asyncio.gather(
                TransportSecurityUtil.validate_replay(self.request, self.kid, nonce),
                TransportSecurityUtil.validate_replay(self.request, self.kid, nonce),
                return_exceptions=True,
            )
            self.assertEqual(sum(result is None for result in results), 1)
            rejected = [result for result in results if isinstance(result, ValueError)]
            self.assertEqual(len(rejected), 1)
            self.assertIn('重放', str(rejected[0]))
            ttl = await self.redis.ttl(self.keys[0])
            self.assertGreater(ttl, 0)
            self.assertLessEqual(ttl, TransportCryptoConfig.transport_crypto_replay_ttl_seconds)
            await TransportSecurityUtil.validate_replay(self.request, self.kid, self.nonce())

    async def test_required_mode_fails_closed_on_injected_set_failure(self):
        # 仅对SET调用注入连接异常；不停止Redis服务，不把故障注入当作真实断网。
        nonce = self.nonce()
        with (patch.object(TransportCryptoConfig, 'transport_crypto_mode', 'required'),
              patch.object(self.redis, 'set', side_effect=ConnectionError('测试连接不可用'))):
            with self.assertRaisesRegex(ValueError, '防重放校验不可用'):
                await TransportSecurityUtil.validate_replay(self.request, self.kid, nonce)
        self.assertFalse(await self.redis.exists(self.keys[0]))
