"""执行过程只展示已有证据，并保持请求响应脱敏。"""
import unittest
from types import SimpleNamespace
from module_higgsfield.service.generation_trace_service import GenerationTraceService


class GenerationTraceTests(unittest.TestCase):
    def test_milestone_and_old_event(self):
        event = SimpleNamespace(sequence=2, occurred_time='time', event_type='task.state',
                                payload={'stage': 'worker_claimed', 'orchestrationState': 'accepted'})
        self.assertEqual(GenerationTraceService.event(event)['label'], '后台已领取任务')
        event.payload = {'orchestrationState': 'accepted'}
        self.assertEqual(GenerationTraceService.event(event)['label'], '任务已保存，等待后台领取')

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
