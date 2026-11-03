"""使用合成契约样例验证视频响应，不代表供应商真实联调。"""

import json
import unittest
from decimal import Decimal

from module_higgsfield.service.videoplus_response_service import VideoPlusResponseService as Parser


class VideoPlusResponseTests(unittest.TestCase):
    def test_h3_seconds_and_images_are_not_video_tokens(self):
        fact = Parser.polling(200, {'task': {'id': 'h3-task', 'status': 'succeeded',
            'content': {'url': 'https://example.com/video.mp4'}, 'resolution': '2K',
            'usage': {'total_seconds': 10.5, 'image_count': 7}}}, expected_task_id='h3-task')
        self.assertEqual(fact.usage_fact.output_seconds, Decimal('10.5'))
        self.assertEqual(fact.usage_fact.image_count, 7)
        self.assertIsNone(fact.usage_fact.video_tokens)
        self.assertEqual(len(fact.outputs), 1)
        self.assertEqual(fact.actual_parameters['resolution'], '2K')
        # JSONB 元数据必须可序列化，不能把 Decimal 直接交给数据库。
        json.dumps(fact.model_dump(mode='json', exclude={'outputs'}))

    def test_poll_business_error_never_becomes_success(self) -> None:
        for base in ({'status_code': 1}, {'status_code': False}, {}, None):
            fact = Parser.polling(200, {
                'id': 'task', 'status': 'succeeded', 'base_resp': base,
                'content': {'video_url': 'https://example.com/video.mp4'},
                'usage': {'completion_tokens': 77260},
            }, expected_task_id='task')
            self.assertEqual(fact.upstream_state, 'unknown')
            self.assertEqual(fact.outputs, [])
            self.assertEqual(fact.usage, {})

    @staticmethod
    def envelope(content: str) -> dict:
        return {'id': 'outer-response', 'choices': [{'message': {'content': content}}]}

    def test_submission_keeps_inner_and_outer_ids_distinct(self) -> None:
        for inner in ({'id': 'inner-task'}, {'id': 'inner-task', 'status': 'queued', 'base_resp': {'status_code': 0}}):
            result = Parser.submission(200, self.envelope(json.dumps(inner)))
            self.assertEqual(result.acceptance, 'accepted')
            self.assertEqual(result.upstream_task_id, 'inner-task')
            self.assertEqual(result.response_id, 'outer-response')

    def test_ambiguous_or_error_submission_never_assumes_safe_retry(self) -> None:
        for content in (
            'not json',
            '[]',
            '{"id":"one","id":"two"}',
            '{"id":"task","base_resp":{}}',
            '{"id":"task","base_resp":{"status_code":true}}',
            '{"id":"task","base_resp":{"status_code":1}}',
            '{"status":"queued"}',
            '{"id":"task","status":"failed"}',
            '{"id":"https://secret.example/token"}',
        ):
            with self.subTest(content=content):
                result = Parser.submission(200, self.envelope(content))
                self.assertEqual(result.acceptance, 'unknown')
                self.assertIsNone(result.upstream_task_id)
        self.assertEqual(Parser.submission(429, self.envelope('{"id":"task"}')).acceptance, 'unknown')

    def test_poll_success_output_and_usage_are_independent(self) -> None:
        body = {
            'id': 'task',
            'status': 'completed',
            'content': {'video_url': 'https://example.com/video?secret=abc'},
            'duration': 5,
            'resolution': '720p',
            'ratio': '16:9',
            'generate_audio': False,
        }
        fact = Parser.polling(200, body, expected_task_id='task')
        self.assertEqual(fact.upstream_state, 'succeeded')
        self.assertEqual(len(fact.outputs), 1)
        self.assertEqual(fact.usage, {})
        self.assertIn('USAGE_MISSING', fact.issues)
        self.assertEqual(fact.outputs[0].actual_metadata.duration_seconds, '5')
        self.assertNotIn('secret=abc', repr(fact))
        body.pop('content')
        body['usage'] = {'completion_tokens': 368100, 'total_tokens': 368100}
        fact = Parser.polling(200, body, expected_task_id='task')
        self.assertEqual(fact.upstream_state, 'succeeded')
        self.assertEqual(fact.outputs, [])
        self.assertEqual(fact.usage['completionTokens'], '368100')
        self.assertIn('OUTPUT_URL_MISSING_OR_INVALID', fact.issues)

    def test_poll_identity_unknown_expired_and_invalid_usage(self) -> None:
        for status, expected in (
            ('queued', 'queued'),
            ('in_progress', 'running'),
            ('expired', 'failed'),
            ('new', 'unknown'),
        ):
            fact = Parser.polling(200, {'id': 'task', 'status': status}, expected_task_id='task')
            self.assertEqual(fact.upstream_state, expected)
        self.assertEqual(fact.issues, ['UPSTREAM_STATUS_UNKNOWN'])
        fact = Parser.polling(200, {'id': 'other', 'status': 'succeeded'}, expected_task_id='task')
        self.assertEqual(fact.upstream_state, 'unknown')
        for value in (True, -1, 1.5, '30', 9223372036854775808):
            fact = Parser.polling(
                200,
                {
                    'id': 'task',
                    'status': 'succeeded',
                    'usage': {'completion_tokens': value},
                    'content': {'video_url': 'http://example.com/insecure'},
                },
                expected_task_id='task',
            )
            self.assertEqual(fact.usage, {})
            self.assertEqual(fact.outputs, [])
            self.assertIn('USAGE_VALUE_INVALID', fact.issues)
