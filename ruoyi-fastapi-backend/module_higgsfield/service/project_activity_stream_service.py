"""项目 SSE 仅发送失效通知；每次推送前重验权限，重连以授权快照恢复。"""
import asyncio
import time
import logging
from config.database import DataSourceRegistry
from exceptions.exception import AuthException, PermissionException, ServiceWarning
from module_admin.service.login_service import LoginService
from module_higgsfield.service.generation_activity_service import GenerationActivityService
from module_higgsfield.service.project_activity_hub import project_activity_hub
from module_higgsfield.service.task_event_service import TaskEventService


class ProjectActivityStreamService:
    CHECK_SECONDS = 5
    SYNC_SECONDS = 30

    @staticmethod
    async def authorize(db, user, project_id):
        if user.user.status != '0' or user.user.del_flag != '0':
            raise AuthException(message='账户不可用')
        return await GenerationActivityService.scope(db, user, project_id)

    @classmethod
    async def stream(cls, request, token, project_id, actor_id, scope, hub=None):
        hub = hub or project_activity_hub
        async with hub.subscribe(project_id, actor_id, scope) as subscription:
            first, synced = True, 0.0
            while not await request.is_disconnected():
                if not first:
                    try:
                        await asyncio.wait_for(subscription.changed.wait(), cls.CHECK_SECONDS)
                    except TimeoutError:
                        pass
                    # 合并生成阶段的密集事件，慢客户端最多保留一个脏标记。
                    await asyncio.sleep(1)
                dirty = subscription.changed.is_set()
                subscription.changed.clear()
                try:
                    async with DataSourceRegistry.session() as db:
                        user = await LoginService._resolve_current_user(request, token, db, refresh_session=False)
                        if user.user.user_id != actor_id:
                            raise AuthException(message='登录身份已变化')
                        current_scope = await cls.authorize(db, user, project_id)
                    # 数据库会话在发送前释放，不让慢连接占用业务连接池。
                    changed_scope = current_scope != subscription.scope
                    subscription.scope = current_scope
                    payload = {'projectId': str(project_id)}
                    if first or changed_scope or time.monotonic() - synced >= cls.SYNC_SECONDS:
                        yield TaskEventService.frame('activity.sync', payload)
                        synced = time.monotonic()
                    elif not hub.healthy:
                        yield TaskEventService.frame('activity.degraded', payload)
                        return
                    elif dirty:
                        yield TaskEventService.frame('activity.changed', payload)
                    else:
                        yield TaskEventService.frame('activity.heartbeat', payload)
                    first = False
                except (AuthException, PermissionException, ServiceWarning):
                    yield TaskEventService.frame('access.revoked', {'reason': 'permission_changed'})
                    return
                except Exception as error:
                    logging.getLogger(__name__).warning('项目事件流暂不可用：%s', type(error).__name__)
                    yield TaskEventService.frame('activity.degraded', {'projectId': str(project_id)})
                    return
