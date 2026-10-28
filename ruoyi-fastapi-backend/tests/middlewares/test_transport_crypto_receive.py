"""加密正文回放后保留真实断开事件，防止SSE断开监听忙循环。"""
import asyncio
import unittest

from middlewares.transport_crypto_middleware import TransportCryptoMiddleware


class TransportReceiveTests(unittest.IsolatedAsyncioTestCase):
    async def test_replays_body_once_then_waits_for_disconnect(self):
        disconnected = asyncio.Event()
        calls = []

        async def receive():
            calls.append('wait')
            await disconnected.wait()
            return {'type': 'http.disconnect'}

        replay = TransportCryptoMiddleware._build_receive(b'plaintext', receive)
        self.assertEqual(await replay(), {'type': 'http.request', 'body': b'plaintext', 'more_body': False})
        self.assertEqual(calls, [])
        waiting = asyncio.create_task(replay())
        await asyncio.sleep(0)
        self.assertFalse(waiting.done())
        self.assertEqual(calls, ['wait'])
        disconnected.set()
        self.assertEqual(await asyncio.wait_for(waiting, 1), {'type': 'http.disconnect'})

    async def test_disconnect_wait_remains_cancellable(self):
        async def receive():
            await asyncio.Event().wait()

        replay = TransportCryptoMiddleware._build_receive(b'', receive)
        await replay()
        waiting = asyncio.create_task(replay())
        await asyncio.sleep(0)
        waiting.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiting
