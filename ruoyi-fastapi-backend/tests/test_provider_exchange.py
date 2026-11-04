"""调用证据的先保存后发送、脱敏、失败事实与只读 cURL 验证。"""

import json
import shlex
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from pydantic import SecretStr

from module_higgsfield.service.provider_exchange_service import ProviderExchangeService as Evidence
from module_higgsfield.service.provider_http_service import ProviderHttpResult


class ExchangeTests(unittest.IsolatedAsyncioTestCase):
    async def test_interrupted_response_records_status_and_diagnostic(self):
        writer = AsyncMock()
        result = ProviderHttpResult('network_error', 200, issue='RESPONSE_BODY_INTERRUPTED',
                                  diagnostic={'phase': 'response_body', 'exceptionType': 'RemoteProtocolError', 'receivedBytes': 10})
        await Evidence.capture(self.transport(writer), 'POST', 'v1/chat/completions', b'{}',
                               'application/json', AsyncMock(return_value=result))
        saved = writer.await_args.args[1]
        self.assertEqual(saved['httpStatus'], 200)
        self.assertEqual(saved['diagnostic'], result.diagnostic)
        self.assertIsNone(saved['response'])

    def transport(self, writer):
        return SimpleNamespace(
            evidence_writer=writer,
            secret=SecretStr('private-test-key'),
            connection=SimpleNamespace(base_url='https://gateway.invalid/', config=SimpleNamespace(biz_id='op')),
        )

    async def test_snapshot_precedes_send_and_does_not_mutate_payload(self):
        records = []

        async def save(identity, evidence):
            records.append((identity, evidence))

        payload = {
            'model': 'mm-imagen2',
            'messages': [{'role': 'user', 'content': "雨夜 '人物'"}],
            'n': 1,
            'size': '2048x1152',
        }

        async def send():
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0][1]['request']['body'], payload)
            return ProviderHttpResult(
                'response', 422, {'error': {'message': '参数不支持', 'api_key': 'private-test-key'}}
            )

        result = await Evidence.capture(
            self.transport(save), 'POST', 'v1/chat/completions', json.dumps(payload).encode(), 'application/json', send
        )
        self.assertEqual(result.http_status, 422)
        self.assertEqual(records[0][0], records[1][0])
        self.assertNotIn('private-test-key', json.dumps(records))
        command = shlex.split(Evidence.curl(records[0][1]['request']))
        self.assertEqual(json.loads(command[command.index('--data-raw') + 1]), payload)

    async def test_failed_evidence_write_never_sends(self):
        send = AsyncMock()
        writer = AsyncMock(side_effect=RuntimeError('证据存储不可用'))
        with self.assertRaises(RuntimeError):
            await Evidence.capture(self.transport(writer), 'GET', 'v1/video/tasks/1', None, 'application/json', send)
        send.assert_not_awaited()

    async def test_timeout_and_invalid_json_are_distinct(self):
        for response in [
            ProviderHttpResult('timeout'),
            ProviderHttpResult('response', 502, issue='RESPONSE_JSON_INVALID'),
        ]:
            writer = AsyncMock()
            send = AsyncMock(return_value=response)
            await Evidence.capture(self.transport(writer), 'GET', 'v1/video/tasks/1', None, 'application/json', send)
            final = writer.await_args.args[1]
            self.assertEqual(final['transport'], response.transport)
            self.assertEqual(final['httpStatus'], response.http_status)
            self.assertIsNone(final['response'])
            send.assert_awaited_once()

    def test_nested_media_credentials_and_cost_are_removed(self):
        body = {
            'choices': [
                {
                    'message': {
                        'content': json.dumps(
                            {
                                'images': [{'b64_json': 'A' * 100000}],
                                'video_url': 'https://files.invalid/video?signature=abc',
                            }
                        )
                    }
                }
            ],
            'error': {'message': 'private-test-key Bearer credential'},
            'access_token': 'secret-token',
            '_platformGatewayHeaders': {'responseCost': '123.45'},
        }
        safe = json.dumps(Evidence.redact(body, 'private-test-key'))
        for secret in ['private-test-key', 'secret-token', 'signature=abc', '123.45', 'A' * 100]:
            self.assertNotIn(secret, safe)
        self.assertLess(len(safe), 2000)

    def test_response_has_bounded_display_size(self):
        safe = Evidence.redact(['图' * 40000] * 100)
        self.assertLess(len(json.dumps(safe, ensure_ascii=False)), 110000)

    async def test_json_prompt_keeps_string_and_non_json_error_is_visible(self):
        writer = AsyncMock()
        payload = {'messages': [{'content': '{"画面":"雨夜"}'}]}
        response = ProviderHttpResult(
            'response', 502, issue='RESPONSE_JSON_INVALID', diagnostic_body='<html>网关故障 private-test-key</html>'
        )
        await Evidence.capture(
            self.transport(writer),
            'POST',
            'v1/chat/completions',
            json.dumps(payload).encode(),
            'application/json',
            AsyncMock(return_value=response),
        )
        self.assertEqual(writer.await_args_list[0].args[1]['request']['body'], payload)
        result = writer.await_args.args[1]
        self.assertIn('网关故障', result['response'])
        self.assertNotIn('private-test-key', result['response'])

    def test_upload_does_not_offer_fake_replay_command(self):
        self.assertIsNone(Evidence.curl({'headers': {'Content-Type': 'multipart/form-data; boundary=test'}}))
