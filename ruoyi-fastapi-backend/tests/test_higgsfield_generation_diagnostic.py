"""诊断只依据同任务的固定调用事实，未知与失败不得混淆。"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from module_higgsfield.service.generation_diagnostic_service import GenerationDiagnosticService as Service
from module_higgsfield.service.task_event_service import TaskEventService


class GenerationDiagnosticTests(unittest.IsolatedAsyncioTestCase):
    def job(self, **changes):
        return SimpleNamespace(**(dict(job_id=1, credential_version_id=7, upstream_state='4',
                                      orchestration_state='5', upstream_task_id='original') | changes))

    def call(self, **changes):
        return SimpleNamespace(**(dict(job_id=1, credential_version_id=7, state='2', operation='video_submit',
                                      acceptance='rejected', http_status=403, request_metadata={},
                                      response_metadata={'message': 'secret-key', 'url': 'private-url'}) | changes))

    def test_rejection_and_unknown_are_distinct_and_no_raw_text_is_exposed(self):
        result = Service.project(self.job(), self.call())
        self.assertEqual(result['code'], 'SUBMISSION_AUTH_REJECTED')
        self.assertNotIn('secret', str(result))
        self.assertNotIn('private-url', str(result))
        job = self.job(upstream_state='6', orchestration_state='3')
        call = self.call(acceptance='unknown', http_status=403, response_metadata={})
        self.assertIsNone(Service.project(job, call))
        call.response_metadata = {'transport': 'timeout'}
        self.assertEqual(Service.project(job, call)['code'], 'SUBMISSION_TIMEOUT')

    def test_poll_reason_requires_original_binding_and_matching_current_state(self):
        call = self.call(operation='video_poll', acceptance='not_applicable',
                         request_metadata={'upstreamTaskId': 'original'},
                         response_metadata={'upstreamState': 'failed', 'failureReason': 'expired'})
        self.assertEqual(Service.project(self.job(), call)['code'], 'UPSTREAM_TASK_EXPIRED')
        self.assertIsNone(Service.project(self.job(upstream_state='3'), call))
        call.request_metadata = {'upstreamTaskId': 'other'}
        self.assertIsNone(Service.project(self.job(), call))

    def test_wrong_identity_credential_or_inflight_record_cannot_supply_reason(self):
        for changes in ({'job_id': 2}, {'credential_version_id': 8}, {'state': '1'}):
            with self.subTest(changes=changes):
                self.assertIsNone(Service.project(self.job(), self.call(**changes)))

    async def test_healthy_task_does_not_read_stale_failure_call(self):
        with patch('module_higgsfield.service.generation_diagnostic_service.GenerationReadDao.latest_execution_call', AsyncMock()) as read:
            self.assertIsNone(await Service.read(None, self.job(upstream_state='3')))
            read.assert_not_awaited()

    async def test_changed_poll_diagnostic_refreshes_stream_without_new_job_event(self):
        snapshot = dict(eventCursor='1:7', allowedActions=[], elementDestination=None,
                        outputs=[], outputsVisibility='visible', billingVisibility='hidden', diagnostic=None)
        with patch('module_higgsfield.service.task_event_service.GenerationReadService.snapshot', AsyncMock(return_value=snapshot)), patch(
            'module_higgsfield.service.task_event_service.TaskEventDao.after', AsyncMock(return_value=[])
        ):
            _, seq, visibility = await TaskEventService.batch(None, None, 1, None)
            snapshot['diagnostic'] = dict(code='QUERY_RESPONSE_INVALID', phase='poll', message='查询响应异常')
            frames, new_seq, new_visibility = await TaskEventService.batch(None, None, 1, seq, visibility)
            self.assertEqual(seq, new_seq)
            self.assertIn('stream.reset', frames[0])
            self.assertIn('QUERY_RESPONSE_INVALID', frames[0])
            self.assertNotEqual(visibility, new_visibility)

    def test_poll_issues_use_fixed_whitelist(self):
        call = self.call(operation='video_poll', request_metadata={'upstreamTaskId': 'original'},
                         response_metadata={'issues': ['secret-key', 'TASK_ID_MISMATCH']})
        result = Service.project(self.job(upstream_state='6'), call)
        self.assertEqual(result['code'], 'TASK_ID_MISMATCH')
        self.assertNotIn('secret', str(result))
