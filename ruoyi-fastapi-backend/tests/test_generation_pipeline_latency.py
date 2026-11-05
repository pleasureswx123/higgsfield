"""回环网络与调度实验：不接触真实供应商，不产生付费任务。"""
import asyncio
import unittest
from types import SimpleNamespace

from pydantic import SecretStr
from module_higgsfield.entity.vo.provider_vo import ConnectionFields
from module_higgsfield.service.bounded_dispatch_service import serve_bounded
from module_higgsfield.service.provider_connection_pool import provider_pool_scope
from module_higgsfield.service.provider_http_service import ProviderHttpService
from module_higgsfield.service.generation_trace_service import GenerationTraceService
from module_higgsfield.service.provider_poll_service import ProviderPollService
from module_higgsfield.service.provider_exchange_service import ProviderExchangeService


class DispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_free_slot_refills_before_slow_task_finishes(self):
        stop, release, third = asyncio.Event(), asyncio.Event(), asyncio.Event()
        queue, active, peak = [1, 2, 3], set(), 0

        async def claim(limit):
            items = queue[:limit]
            del queue[:limit]
            return items

        async def execute(item):
            nonlocal peak
            active.add(item)
            peak = max(peak, len(active))
            try:
                if item == 1:
                    await release.wait()
                if item == 3:
                    self.assertIn(1, active)
                    third.set()
            finally:
                active.remove(item)

        worker = asyncio.create_task(serve_bounded(stop, 2, claim, execute))
        try:
            await asyncio.wait_for(third.wait(), 2)
            self.assertLessEqual(peak, 2)
            stop.set()
            await asyncio.sleep(0)
            self.assertFalse(worker.done())
            release.set()
            await asyncio.wait_for(worker, 2)
            self.assertFalse(active)
        finally:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)


class NetworkMilestoneTests(unittest.IsolatedAsyncioTestCase):
    async def test_response_survives_display_evidence_failure(self):
        result = SimpleNamespace(transport='response', http_status=200, issue=None,
                                 diagnostic=None, body={'id': 'accepted'}, diagnostic_body=None)
        calls = []

        async def save(identity, evidence):
            if 'finishedAt' in evidence:
                raise OSError('模拟日志存储故障')

        async def action():
            calls.append('request')
            return result

        transport = SimpleNamespace(evidence_writer=save, secret=SecretStr('test'),
                                    connection=SimpleNamespace(base_url='http://localhost',
                                                               config=SimpleNamespace(biz_id='test')))
        with self.assertLogs('module_higgsfield.service.provider_exchange_service', level='WARNING'):
            received = await ProviderExchangeService.capture(transport, 'POST', '/generate', b'{}',
                                                            'application/json', action)
        self.assertIs(received, result)
        self.assertEqual(calls, ['request'])
        self.assertIsNone(transport.network_trace)

        async def fail_before_send(identity, evidence):
            raise OSError('模拟发送前存储故障')

        transport.evidence_writer = fail_before_send
        with self.assertRaises(OSError):
            await ProviderExchangeService.capture(transport, 'POST', '/generate', b'{}',
                                                  'application/json', action)
        self.assertEqual(calls, ['request'])

    async def test_sent_before_response_and_connection_reuse_without_cookie_leak(self):
        release, sent = asyncio.Event(), asyncio.Event()
        connections, requests, handlers = [], [], set()

        async def respond(reader, writer):
            handlers.add(asyncio.current_task())
            connections.append(writer.get_extra_info('peername'))
            try:
                while True:
                    headers = await reader.readuntil(b'\r\n\r\n')
                    lines = headers.decode().split('\r\n')
                    fields = dict((line.split(': ', 1)[0].lower(), line.split(': ', 1)[1]) for line in lines if ': ' in line)
                    await reader.readexactly(int(fields.get('content-length', '0')))
                    requests.append(fields)
                    await release.wait()
                    writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nSet-Cookie: private=first-account\r\n\r\n{}')
                    await writer.drain()
            except (asyncio.IncompleteReadError, ConnectionError):
                pass
            finally:
                writer.close()
                await writer.wait_closed()
                handlers.discard(asyncio.current_task())

        server = await asyncio.start_server(respond, '127.0.0.1', 0)
        config = ConnectionFields(name='回环测试', baseUrl=f'http://127.0.0.1:{server.sockets[0].getsockname()[1]}/', adapterVersion='videoplus-v1', config={'allowedHosts': ['127.0.0.1'], 'connectTimeoutSeconds': 2, 'readTimeoutSeconds': 5, 'operationTimeoutSeconds': 5, 'taskTimeoutSeconds': 60})
        records = {}

        async def save(identity, evidence):
            records.setdefault(identity, {}).update(evidence)
            if evidence.get('requestSentAt'):
                sent.set()

        try:
            async with provider_pool_scope(2):
                first = ProviderHttpService(config, SecretStr('first-account'))
                first.evidence_writer = save
                pending = asyncio.create_task(first.submit({'model': 'test'}))
                try:
                    await asyncio.wait_for(sent.wait(), 3)
                    self.assertFalse(pending.done())
                    call = SimpleNamespace(request_metadata={'exchanges': records})
                    self.assertEqual(GenerationTraceService.request_state(call), 'awaiting_response')
                    self.assertFalse(next(iter(records.values())).get('finishedAt'))
                    release.set()
                    self.assertEqual((await pending).http_status, 200)
                    final = next(iter(records.values()))
                    self.assertIn('http11.send_request_body', final['timingsMs'])
                    self.assertIn('responseBodyAt', final)
                    second = ProviderHttpService(config, SecretStr('second-account'))
                    self.assertEqual((await second.poll('test')).http_status, 200)
                    self.assertEqual(len(connections), 1)
                    self.assertEqual(len(requests), 2)
                    self.assertNotIn('cookie', requests[1])
                    self.assertEqual(requests[1]['authorization'], 'Bearer second-account')
                finally:
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
        finally:
            release.set()
            server.close()
            await server.wait_closed()
            for handler in list(handlers):
                handler.cancel()
            await asyncio.gather(*handlers, return_exceptions=True)

    def test_prepare_does_not_unlock_button(self):
        call = SimpleNamespace(request_metadata={'exchanges': {'one': {'startedAt': 'time'}}})
        self.assertEqual(GenerationTraceService.request_state(call), 'preparing_request')

    def test_poll_cadence_keeps_existing_rate_boundary(self):
        for _ in range(50):
            self.assertTrue(30 <= ProviderPollService.next_delay('running') <= 35)
            self.assertTrue(45 <= ProviderPollService.next_delay('queued') <= 60)
            self.assertEqual(ProviderPollService.next_delay('unknown'), 60)
