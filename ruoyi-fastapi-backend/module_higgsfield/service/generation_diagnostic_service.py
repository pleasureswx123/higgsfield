"""从已记录调用事实生成固定脱敏说明，不展示供应商自由文本。"""

from module_higgsfield.dao.generation_read_dao import GenerationReadDao
from module_higgsfield.service.preparation_diagnostic_service import PreparationDiagnosticService


class GenerationDiagnosticService:
    @staticmethod
    def project(job, call):
        if (call is None or call.job_id != job.job_id
                or call.credential_version_id != job.credential_version_id or call.state not in {'2', '3'}):
            return None
        data = call.response_metadata if isinstance(call.response_metadata, dict) else {}
        phase = 'poll' if call.operation == 'video_poll' else 'submit'
        code, message = None, None
        if phase == 'poll':
            request = call.request_metadata if isinstance(call.request_metadata, dict) else {}
            if not job.upstream_task_id or request.get('upstreamTaskId') != job.upstream_task_id:
                return None
            if job.upstream_state == '4' and data.get('upstreamState') == 'failed':
                if data.get('failureReason') == 'expired':
                    code, message = 'UPSTREAM_TASK_EXPIRED', '供应商查询结果表明原生成任务已过期。'
                elif data.get('failureReason') == 'failed':
                    code, message = 'UPSTREAM_TASK_FAILED', '供应商查询结果表明生成执行失败，未提供可发布的更具体原因。'
            elif job.upstream_state == '6':
                issues = data.get('issues') if isinstance(data.get('issues'), list) else []
                known = {
                    'TASK_ID_MISMATCH': '查询响应的任务编号与原任务不一致，结果不能采信。',
                    'QUERY_RESPONSE_INVALID': '查询响应不符合预期协议，暂不能确认上游结果。',
                    'UPSTREAM_STATUS_UNKNOWN': '查询返回了未识别的任务状态，需要管理员核查。',
                    'QUERY_TRANSPORT_UNKNOWN': '查询未取得确定响应，暂不能确认上游结果。',
                }
                for item, text in known.items():
                    if item in issues:
                        code, message = item, text
                        break
        elif call.operation in {'image', 'video_submit'}:
            if job.upstream_state == '4' and call.acceptance == 'rejected':
                code, message = 'SUBMISSION_REJECTED', '供应商提交结果明确拒绝本次请求。'
                if call.http_status in {401, 403}:
                    code, message = 'SUBMISSION_AUTH_REJECTED', '供应商在提交阶段拒绝了身份或访问授权，请管理员核查接入配置。'
                elif call.http_status == 429:
                    code, message = 'SUBMISSION_RATE_REJECTED', '供应商在提交阶段明确拒绝请求，并返回请求频率或额度限制状态。'
            elif job.orchestration_state == '3' and call.acceptance == 'unknown':
                transport = data.get('transport')
                if transport == 'timeout':
                    code, message = 'SUBMISSION_TIMEOUT', '提交等待响应超时，不能据此判断供应商未受理。'
                elif transport == 'network_error':
                    code, message = 'SUBMISSION_NETWORK_UNKNOWN', '提交通信发生错误，不能据此判断供应商未受理。'
        return {'code': code, 'phase': phase, 'message': message} if code else None

    @classmethod
    async def read(cls, db, job):
        if job.orchestration_state in {'0', '1'}:
            return await PreparationDiagnosticService.read(db, job)
        if job.upstream_state not in {'4', '6'} and job.orchestration_state != '3':
            return None
        return cls.project(job, await GenerationReadDao.latest_execution_call(db, job.job_id))
