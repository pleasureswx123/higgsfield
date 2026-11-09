"""按已持久化证据展示执行过程，未观察到的节点不推测为成功。"""
from module_higgsfield.dao.generation_trace_dao import GenerationTraceDao
from module_higgsfield.service.provider_exchange_service import ProviderExchangeService


class GenerationTraceService:
    @staticmethod
    def request_state(call):
        """发送意图与实际调用证据分开；HTTP 成功也不直接等同生成成功。"""
        if call is None:
            return 'not_started'
        exchanges = (call.request_metadata or {}).get('exchanges', {})
        if not exchanges:
            return 'preparing_request'
        # 以最后一次交换为准；收到响应头不代表响应正文完整到达。
        # PostgreSQL JSONB 不保留字典插入顺序，必须按实际开始时间选择。
        latest = max(exchanges.values(), key=lambda row: row.get('startedAt') or '')
        if latest.get('finishedAt'):
            return 'response_received' if latest.get('transport') == 'response' else 'transport_error'
        if latest.get('requestSentAt'):
            return 'awaiting_response'
        return 'preparing_request'

    STAGES = {
        'manual_review_required': '自动核查已暂停，等待管理员核实供应商状态',
        'manual_requery': '管理员恢复原任务状态核查',
        'worker_claimed': '后台已领取任务',
        'references_preparing': '开始准备参考图与请求参数',
        'references_ready': '参考图与请求参数准备完成',
        'response_received': '已收到供应商响应',
        'results_saving': '响应解析完成，开始保存结果',
    }
    STATES = {
        'accepted': '任务已保存，等待后台领取', 'preparing': '开始校验生成配置',
        'submitting': '发送意图已保存，开始调用供应商',
        'submission_unknown': '调用结果未确认', 'running': '供应商任务处理中',
        'finished': '任务执行结束', 'blocked': '任务执行受阻',
    }

    @classmethod
    def event(cls, event):
        data = event.payload or {}
        if data.get('downloadProgress'):
            return None
        label = cls.STAGES.get(data.get('stage'))
        if not label and event.event_type == 'task.state':
            label = cls.STATES.get(data.get('orchestrationState'))
        if event.event_type == 'output.state':
            label = {'not_started': '生成结果已发现，等待保存',
                     'archived': '结果已保存', 'archive_failed': '结果保存失败',
                     'archiving': '正在保存结果', 'source_expired': '结果源地址已过期'}.get(data.get('archiveState'))
        if event.event_type == 'task.problem':
            label = '执行遇到问题'
        return {'id': str(event.sequence), 'time': event.occurred_time, 'label': label} if label else None

    @staticmethod
    def call(call, *, include_body=True):
        metadata = call.request_metadata or {}
        exchanges = []
        for row in sorted(metadata.get('exchanges', {}).values(), key=lambda item: item.get('startedAt') or '')[-20:]:
            request = row.get('request') or {}
            exchanges.append({
                'startedAt': row.get('startedAt'), 'finishedAt': row.get('finishedAt'),
                'requestSentAt': row.get('requestSentAt'), 'responseHeadersAt': row.get('responseHeadersAt'),
                'responseBodyAt': row.get('responseBodyAt'), 'timingsMs': row.get('timingsMs', {}),
                'requestBodyBytes': row.get('requestBodyBytes'),
                'requestBodySha256': row.get('requestBodySha256'),
                'httpStatus': row.get('httpStatus'), 'transport': row.get('transport'),
                'request': ProviderExchangeService.redact(request.get('body')) if include_body else None,
                'response': ProviderExchangeService.redact(row.get('response')) if include_body else None,
                'issue': ProviderExchangeService.redact(row.get('issue')),
                'diagnostic': {key: (row.get('diagnostic') or {}).get(key)
                               for key in ('exceptionType', 'receivedBytes', 'phase', 'failedPhase',
                                           'lastStartedPhase', 'errorChain', 'traceErrorChain',
                                           'connectTimeoutSeconds', 'readTimeoutSeconds', 'operationTimeoutSeconds',
                                           'trustEnvironmentProxy', 'followRedirects', 'automaticRetries',
                                            'httpxVersion', 'httpVersion', 'responseHeaders', 'outboundLocalAddress',
                                           'newConnectionObserved', 'peerIp', 'peerPort')},
            })
        return {'id': str(call.call_id), 'operation': call.operation,
                'httpStatus': call.http_status, 'acceptance': call.acceptance,
                'startedAt': call.started_time, 'finishedAt': call.finished_time,
                'exchanges': exchanges}

    @classmethod
    async def read(cls, db, job, *, include_body=True):
        events = await GenerationTraceDao.events(db, job.job_id)
        calls = await GenerationTraceDao.calls(db, job.job_id)
        timeline = []
        previous = None
        for event in events:
            item = cls.event(event)
            if item is not None:
                item['sincePreviousMs'] = max(0, round((event.occurred_time - previous).total_seconds() * 1000)) if previous else None
                previous = event.occurred_time
                timeline.append(item)
        return {'attemptCount': job.attempt_count,
                'events': timeline,
                'calls': [cls.call(call, include_body=include_body) for call in calls]}
