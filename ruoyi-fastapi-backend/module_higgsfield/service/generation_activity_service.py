"""合并个人进行中状态与授权项目数量；不会触发调度或供应商请求。"""

from exceptions.exception import PermissionException
from module_higgsfield.dao.production_capacity_dao import ProductionCapacityDao
from module_higgsfield.dao.generation_activity_dao import GenerationActivityDao
from module_higgsfield.dao.generated_output_dao import GeneratedOutputDao
from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.dao.project_workspace_dao import WorkspaceDao
from module_higgsfield.service.generation_read_service import GenerationReadService
from module_higgsfield.service.generation_trace_service import GenerationTraceService
from module_higgsfield.service.project_workspace_service import WorkspaceService


class GenerationActivityService:
    @staticmethod
    async def scope(db, user, project_id):
        if '*:*:*' not in user.permissions and 'generation:read' not in user.permissions:
            raise PermissionException(message='没有读取生成任务的权限')
        _, role, _ = await WorkspaceService.authorize(db, user, int(project_id), 'generation:read', owner_id=user.user.user_id)
        scopes = await WorkspaceDao.permission_scopes(db, role, int(project_id))
        if scopes.get('generation:read') not in {'own', 'project'}:
            raise PermissionException(message='没有读取生成任务的权限')
        return scopes['generation:read']

    @classmethod
    async def read(cls, db, user, query):
        scope = await cls.scope(db, user, query.project_id)
        rows, count, has_next = await GenerationActivityDao.read(db, user.user.user_id, query, scope)
        identities = [row.job_id for row in rows]
        summaries = await GeneratedOutputDao.archive_summaries(db, identities)
        stages, calls = await GenerationActivityDao.execution(db, identities)
        waiting = await ProductionCapacityDao.waiting_reasons(db, rows)
        return {
            'projectActiveCount': count, 'hasNext': has_next,
            'rows': [{
                'id': str(row.job_id), 'projectId': str(row.project_id),
                'folderId': row.input_snapshot.get('folderId'),
                'promptExcerpt': GenerationReadService.prompt_excerpt(row),
                'kind': row.kind, 'createTime': row.create_time, 'revision': str(row.revision),
                'orchestrationState': JobEventDao.ORCHESTRATION[int(row.orchestration_state)],
                'upstreamState': JobEventDao.UPSTREAM[int(row.upstream_state)],
                'archiveSummary': summaries[row.job_id],
                'billingState': ('pending', 'calculated', 'confirmed', 'disputed')[int(row.billing_state)],
                'allowedActions': [], 'executionStage': stages.get(row.job_id),
                'queueReason': waiting.get(row.job_id),
                'requestState': GenerationTraceService.request_state(calls.get(row.job_id)),
            } for row in rows],
        }
