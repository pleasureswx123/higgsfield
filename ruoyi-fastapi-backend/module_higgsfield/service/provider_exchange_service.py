"""保存发送时的脱敏交换证据；查询不会重新编译或发送请求。"""

import json
import re
import shlex
from datetime import datetime, timezone
from uuid import uuid4
from time import perf_counter

from module_higgsfield.dao.provider_call_dao import ProviderCallDao
from module_higgsfield.service.job_lease_service import JobLeaseService


class ProviderExchangeService:
    @classmethod
    def redact(cls, value, secret='', depth=0, budget=None, parse_embedded=True):
        budget = budget if budget is not None else [100000]
        if budget[0] <= 0:
            return '[展示容量已达上限]'
        budget[0] -= 1
        if depth > 16:
            return '[已省略深层内容]'
        if isinstance(value, dict):
            result = {}
            for key, item in list(value.items())[:200]:
                if re.search(
                    r'authorization|cookie|secret|api.?key|password|b64|base64|signature|access.?token|refresh.?token|credential|cost|price|balance|_platformGatewayHeaders',
                    key,
                    re.I,
                ):
                    result[key] = '[已脱敏]'
                else:
                    result[key] = cls.redact(item, secret, depth + 1, budget, parse_embedded)
            if len(value) > 200:
                result['_omittedFields'] = len(value) - 200
            return result
        if isinstance(value, list):
            result = [cls.redact(item, secret, depth + 1, budget, parse_embedded) for item in value[:100]]
            return result + ([f'[另有 {len(value) - 100} 项已省略]'] if len(value) > 100 else [])
        if isinstance(value, str):
            if secret:
                value = value.replace(secret, '[密钥已脱敏]')
            # 图片接口可能将完整 JSON 放在 content 中，先解析再删除媒体正文。
            if parse_embedded and value.lstrip().startswith(('{', '[')):
                try:
                    return cls.redact(json.loads(value), secret, depth + 1, budget)
                except (ValueError, RecursionError):
                    pass
            value = re.sub(r'data:[^\s"\']+', '[内嵌媒体已省略]', value)
            value = re.sub(r'https?://[^\s"\'<>]+', '[媒体或外部地址已脱敏]', value)
            value = re.sub(r'(?i)bearer\s+\S+|sk-[\w-]+', '[凭据已脱敏]', value)
            limit = min(32000, budget[0])
            budget[0] -= min(len(value), limit)
            return value[:limit] + ('[超长内容已截断]' if len(value) > limit else '')
        return value if value is None or isinstance(value, (bool, int, float)) else '[已省略]'

    @staticmethod
    def curl(request):
        if request['headers'].get('Content-Type', '').startswith('multipart/'):
            return None
        command = 'curl --request ' + shlex.quote(request['method']) + ' ' + shlex.quote(request['url'])
        for key, value in request['headers'].items():
            command += ' --header ' + shlex.quote(f'{key}: {value}')
        if request.get('body') is not None:
            command += ' --data-raw ' + shlex.quote(json.dumps(request['body'], ensure_ascii=False))
        return command

    @staticmethod
    def bind(transport, context, call_id):
        async def save(identity, evidence):
            async with context.sessions() as db:
                await JobLeaseService.guard(db, context.lease)
                call = await ProviderCallDao.locked(db, call_id)
                if call is None or call.job_id != context.lease.job_id:
                    raise ValueError('调用证据与任务不匹配')
                metadata = dict(call.request_metadata)
                exchanges = dict(metadata.get('exchanges', {}))
                previous = exchanges.get(identity, {})
                exchanges[identity] = {**previous, **evidence}
                metadata['exchanges'] = exchanges
                call.request_metadata = metadata
                await db.commit()

        transport.evidence_writer = save

    @classmethod
    async def capture(cls, transport, method, path, content, content_type, action):
        writer = transport.evidence_writer
        if writer is None:
            return await action()
        identity = uuid4().hex
        secret = transport.secret.get_secret_value()
        body = None
        if isinstance(content, bytes):
            try:
                body = cls.redact(json.loads(content), secret, parse_embedded=False)
            except (ValueError, UnicodeError):
                body = '[非 JSON 请求正文已省略]'
        elif content is not None:
            body = '[流式上传文件已省略，参见请求元数据]'
        request = {
            'method': method,
            'url': transport.connection.base_url + path,
            'headers': {
                'Authorization': 'Bearer <YOUR_API_KEY>',
                'X-Biz-Id': cls.redact(transport.connection.config.biz_id, secret),
                'Content-Type': content_type,
                'Accept': 'application/json',
                'Accept-Encoding': 'identity',
            },
            'body': body,
        }
        await writer(
            identity, {'id': identity, 'request': request, 'startedAt': datetime.now(timezone.utc).isoformat()}
        )
        clock = perf_counter()
        timings = {}
        starts = {}
        milestones = {}

        async def trace(name, info):
            # 不保存底层info，里面可能带请求头或连接秘密。
            phase, _, outcome = name.rpartition('.')
            if outcome == 'started':
                starts[phase] = perf_counter()
            elif outcome in {'complete', 'failed'} and phase in starts:
                timings[phase] = round((perf_counter() - starts.pop(phase)) * 1000, 3)
            milestone = None
            if name in {'http11.send_request_body.complete', 'http2.send_request_body.complete'}:
                milestone = 'requestSentAt'
            elif name in {'http11.receive_response_headers.complete', 'http2.receive_response_headers.complete'}:
                milestone = 'responseHeadersAt'
            elif name in {'http11.receive_response_body.complete', 'http2.receive_response_body.complete'}:
                milestone = 'responseBodyAt'
            if milestone:
                milestones[milestone] = datetime.now(timezone.utc).isoformat()
                try:
                    await writer(identity, {**milestones, 'timingsMs': dict(timings)})
                except Exception:
                    # 请求已在传输中，监测存储故障不能打断响应或诱发再次付费调用。
                    milestones['timingWriteDelayed'] = True

        transport.network_trace = trace
        try:
            result = await action()
        finally:
            transport.network_trace = None
        timings['total'] = round((perf_counter() - clock) * 1000, 3)
        await writer(
            identity,
            {
                'finishedAt': datetime.now(timezone.utc).isoformat(),
                **milestones, 'timingsMs': timings,
                'transport': result.transport,
                'httpStatus': result.http_status,
                'issue': result.issue,
                'diagnostic': result.diagnostic,
                'response': cls.redact(result.body if result.body is not None else result.diagnostic_body, secret),
            },
        )
        return result
