"""素材与元素共享的制作流转规则；调用服务负责授权、锁和持久化。"""


class WorkflowError(ValueError):
    """可向用户展示的业务动作错误。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


TRANSITIONS = {
    'reopen': {'approved': 'working'},
    'start': {'none': 'working', 'rejected': 'working'},
    'submit': {'working': 'review'},
    'withdraw': {'review': 'working'},
    'request_changes': {'review': 'rejected'},
    'approve': {'review': 'approved'},
}


def transition(
    state: str,
    action: str,
    *,
    current_version_id: int | None,
    expected_version_id: int | None,
    reason: str | None = None,
) -> str:
    """校验动作针对当前版本且符合前置状态，返回下一状态。

    expected_version_id 必须来自用户看到的版本，不得由服务端自动补当前值。
    幂等重放由调用方在执行本规则前处理，重复点击不产生第二条状态历史。
    """
    if current_version_id is None or expected_version_id is None:
        raise WorkflowError('WORKFLOW_VERSION_REQUIRED', '请先保存内容版本，再执行此操作')
    if current_version_id != expected_version_id:
        raise WorkflowError('WORKFLOW_VERSION_CHANGED', '内容版本已变化，请刷新后查看最新内容')
    target = TRANSITIONS.get(action, {}).get(state)
    if target is None:
        raise WorkflowError('WORKFLOW_TRANSITION_INVALID', '当前状态不能执行此操作，请刷新后重试')
    if action == 'request_changes' and not (reason and reason.strip()):
        raise WorkflowError('WORKFLOW_REASON_REQUIRED', '请填写具体修改意见后退回')
    return target
