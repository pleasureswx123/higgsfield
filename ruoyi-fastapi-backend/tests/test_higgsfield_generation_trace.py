"""执行过程只展示已有证据，并保持请求响应脱敏。"""
import unittest
from types import SimpleNamespace
from module_higgsfield.service.generation_trace_service import GenerationTraceService


class GenerationTraceTests(unittest.TestCase):
    def test_headers_then_timeout_is_transport_error(self):
        for transport in ('timeout', 'network_error'):
            call = SimpleNamespace(request_metadata={'exchanges': {'a': {
                'httpStatus': 200, 'transport': transport, 'finishedAt': 'end',
                'requestSentAt': 'sent', 'responseHeadersAt': 'headers',
            }}})
            self.assertEqual(GenerationTraceService.request_state(call), 'transport_error')

    def test_latest_exchange_controls_request_state(self):
        exchanges = {'b': {'startedAt': '2026-11-05T02:00:00+00:00', 'requestSentAt': 'sent'},
                     'a': {'startedAt': '2026-11-05T01:00:00+00:00',
                           'transport': 'response', 'httpStatus': 200, 'finishedAt': 'end'}}
        call = SimpleNamespace(request_metadata={'exchanges': exchanges})
        self.assertEqual(GenerationTraceService.request_state(call), 'awaiting_response')
        exchanges['b'].update(transport='response', httpStatus=400, finishedAt='end')
        self.assertEqual(GenerationTraceService.request_state(call), 'response_received')

    def test_milestone_and_old_event(self):
        event = SimpleNamespace(sequence=2, occurred_time='time', event_type='task.state',
                                payload={'stage': 'worker_claimed', 'orchestrationState': 'accepted'})
        self.assertEqual(GenerationTraceService.event(event)['label'], '后台已领取任务')
        event.payload = {'orchestrationState': 'accepted'}
        self.assertEqual(GenerationTraceService.event(event)['label'], '任务已保存，等待后台领取')
        event.event_type = 'output.state'
        event.payload = {'archiveState': 'not_started'}
        self.assertEqual(GenerationTraceService.event(event)['label'], '生成结果已发现，等待保存')

    def test_no_response_is_not_success_and_media_secrets_are_redacted(self):
        call = SimpleNamespace(call_id=1, operation='image', http_status=None, acceptance='unknown',
            started_time='start', finished_time=None, request_metadata={'exchanges': {'a': {
                'startedAt': 'start', 'request': {'headers': {'Authorization': 'secret'},
                    'body': {'api_key': 'secret', 'image': 'data:image/png;base64,abc'}}}}})
        result = GenerationTraceService.call(call)
        self.assertIsNone(result['httpStatus'])
        self.assertIsNone(result['exchanges'][0]['response'])
        self.assertNotIn('secret', str(result))
        self.assertNotIn('base64,abc', str(result))
        call.request_metadata['exchanges']['a'].update(httpStatus=400, response={'error': {'message': 'bad size'}}, finishedAt='end')
        result = GenerationTraceService.call(call)
        self.assertEqual(result['exchanges'][0]['httpStatus'], 400)
        self.assertEqual(result['exchanges'][0]['response']['error']['message'], 'bad size')

    def test_exchange_display_is_chronological_after_jsonb_reordering(self):
        call = SimpleNamespace(call_id=1, operation='image', http_status=200, acceptance='accepted',
            started_time='start', finished_time='end', request_metadata={'exchanges': {
                'a': {'startedAt': '2026-11-05T02:00:00+00:00'},
                'z': {'startedAt': '2026-11-05T01:00:00+00:00'},
            }})
        result = GenerationTraceService.call(call)
        self.assertEqual([row['startedAt'] for row in result['exchanges']],
                         ['2026-11-05T01:00:00+00:00', '2026-11-05T02:00:00+00:00'])
