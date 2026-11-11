"""验证制作动作的业务约束，不依赖页面隐藏按钮。"""
import unittest

from module_higgsfield.service.production_workflow import WorkflowError, transition


def move(state, action, **kwargs):
    return transition(state, action, current_version_id=7, expected_version_id=7, **kwargs)


class ProductionWorkflowTests(unittest.TestCase):
    def test_approved_content_can_explicitly_reopen_without_reupload(self):
        self.assertEqual(move('approved', 'reopen'), 'working')
    def test_complete_rework_cycle(self):
        state = move('none', 'start')
        self.assertEqual(state, 'working')
        state = move(state, 'submit')
        self.assertEqual(state, 'review')
        state = move(state, 'request_changes', reason='请修正角色服装颜色')
        self.assertEqual(state, 'rejected')
        state = move(state, 'start')
        state = move(state, 'submit')
        self.assertEqual(move(state, 'approve'), 'approved')

    def test_cannot_approve_without_submission(self):
        for state in ['none', 'working', 'rejected', 'approved']:
            with self.subTest(state=state), self.assertRaisesRegex(WorkflowError, '当前状态'):
                move(state, 'approve')

    def test_return_requires_actionable_feedback(self):
        for reason in [None, '', '   ']:
            with self.subTest(reason=reason), self.assertRaisesRegex(WorkflowError, '修改意见'):
                move('review', 'request_changes', reason=reason)

    def test_stale_version_cannot_be_approved(self):
        with self.assertRaisesRegex(WorkflowError, '版本已变化'):
            transition('review', 'approve', current_version_id=8, expected_version_id=7)

    def test_missing_version_cannot_be_submitted(self):
        with self.assertRaisesRegex(WorkflowError, '版本'):
            transition('working', 'submit', current_version_id=None, expected_version_id=None)

    def test_review_can_be_withdrawn_before_editing(self):
        self.assertEqual(move('review', 'withdraw'), 'working')

    def test_approved_content_requires_new_version_to_resume(self):
        with self.assertRaises(WorkflowError):
            move('approved', 'start')

    def test_duplicate_submission_is_not_a_second_transition(self):
        with self.assertRaises(WorkflowError):
            move('review', 'submit')

    def test_unknown_action_is_rejected(self):
        with self.assertRaises(WorkflowError):
            move('working', 'clear')
