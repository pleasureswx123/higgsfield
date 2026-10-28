"""持久任务事件重放及权限重验；每轮读取使用独立短会话。"""

import asyncio
import json
import re
import time
from fastapi.encoders import jsonable_encoder
from config.database import DataSourceRegistry
from exceptions.exception import AuthException, PermissionException, ServiceWarning
from module_admin.service.login_service import LoginService
from module_higgsfield.dao.task_event_dao import TaskEventDao
from module_higgsfield.service.generation_read_service import GenerationReadService
from module_higgsfield.service.project_workspace_service import WorkspaceService


class TaskEventService:
    @staticmethod
    def cursor(job_id, value):
        if value is None:
            return None
        if not re.fullmatch(r'[1-9][0-9]{0,18}:(0|[1-9][0-9]{0,18})', value):
            WorkspaceService.conflict('EVENT_CURSOR_INVALID', '事件游标格式无效')
        identity, sequence = map(int, value.split(':'))
        if identity != job_id or sequence > 9223372036854775807:
            WorkspaceService.conflict('EVENT_CURSOR_INVALID', '事件游标不属于当前任务或超出范围')
        return sequence

    @staticmethod
    def frame(event, payload, cursor=None):
        body = json.dumps(jsonable_encoder(payload), ensure_ascii=False, separators=(',', ':'))
        return (f'id: {cursor}\n' if cursor else '') + f'event: {event}\ndata: {body}\n\n'

    @classmethod
    async def batch(cls, db, user, job_id, sequence, visibility=None):
        snapshot = await GenerationReadService.snapshot(db, user, job_id)
        latest = int(snapshot['eventCursor'].split(':')[1])
        # 授权或查询诊断变化不一定产生任务事件，仍须主动刷新已打开的详情。
        permission_projection = {
            'actions': sorted(snapshot['allowedActions']),
            'destination': snapshot['elementDestination'],
            'sourceJobId': snapshot.get('sourceJobId'),
            'diagnostic': snapshot.get('diagnostic'),
            'outputs': [
                {
                    'id': row['id'],
                    'actions': sorted(row.get('allowedActions', [])),
                    'preview': bool(row.get('previewUrl')),
                    'download': bool(row.get('downloadUrl')),
                }
                for row in sorted(snapshot['outputs'], key=lambda row: row['id'])
            ],
        }
        current_visibility = (
            snapshot['outputsVisibility'], snapshot['billingVisibility'],
            json.dumps(permission_projection, ensure_ascii=False, sort_keys=True),
        )
        if sequence is None:
            return [cls.frame('task.snapshot', snapshot, snapshot['eventCursor'])], latest, current_visibility
        if sequence > latest:
            WorkspaceService.conflict('EVENT_CURSOR_INVALID', '事件游标超过当前任务序号')
        rows = await TaskEventDao.after(db, job_id, sequence)
        contiguous = all(row.sequence == sequence + index + 1 for index, row in enumerate(rows))
        supported = all(row.event_type in {'task.state', 'output.state'} for row in rows)
        # 输出权限同样约束历史事件；使用脱敏快照推进游标，避免暴露输出编号。
        hidden_outputs = snapshot['outputsVisibility'] == 'hidden' and any(
            row.event_type == 'output.state' for row in rows
        )
        if (
            not contiguous
            or not supported
            or hidden_outputs
            or (not rows and sequence < latest)
            or (visibility is not None and visibility != current_visibility)
        ):
            reset = {'reason': 'gap', 'snapshot': snapshot, 'resumeCursor': snapshot['eventCursor']}
            return [cls.frame('stream.reset', reset, snapshot['eventCursor'])], latest, current_visibility
        if visibility is None and not rows:
            # 新连接没有旧授权投影；游标已追平也要刷新断线期间可能失效的权限。
            return [cls.frame('task.snapshot', snapshot, snapshot['eventCursor'])], latest, current_visibility
        frames = []
        for row in rows:
            # 不直接透传JSON载荷；未实现的事件类型通过快照恢复，不泄露内部字段。
            fields = (
                ('revision', 'orchestrationState', 'upstreamState', 'cancelState')
                if row.event_type == 'task.state'
                else ('outputId', 'revision', 'archiveState')
            )
            payload = {key: row.payload[key] for key in fields if key in row.payload}
            envelope = {
                'schemaVersion': row.schema_version,
                'jobId': str(job_id),
                'sequence': str(row.sequence),
                'occurredAt': row.occurred_time,
                'payload': payload,
            }
            frames.append(cls.frame(row.event_type, envelope, f'{job_id}:{row.sequence}'))
        return frames, rows[-1].sequence if rows else sequence, current_visibility

    @classmethod
    async def stream(cls, request, token, job_id, sequence, initial, visibility):
        for frame in initial:
            yield frame
        yield 'retry: 3000\n\n'
        heartbeat = time.monotonic()
        while not await request.is_disconnected():
            await asyncio.sleep(1)
            try:
                async with DataSourceRegistry.session() as db:
                    user = await LoginService._resolve_current_user(request, token, db, refresh_session=False)
                    if user.user.status != '0' or user.user.del_flag != '0':
                        raise AuthException(message='账户不可用')
                    frames, sequence, visibility = await cls.batch(db, user, job_id, sequence, visibility)
                # 会话及任务锁已释放后才向慢客户端写入数据。
                for frame in frames:
                    yield frame
                if not frames and time.monotonic() - heartbeat >= 15:
                    yield ': heartbeat\n\n'
                    heartbeat = time.monotonic()
            except (AuthException, PermissionException, ServiceWarning):
                yield cls.frame('access.revoked', {'reason': 'permission_changed'})
                return
