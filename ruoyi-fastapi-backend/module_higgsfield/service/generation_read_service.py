"""生成输入仅从固定业务快照投影，内部执行信息不得直接返回。"""

from pydantic import ValidationError
from common.vo import PageModel
from exceptions.exception import PermissionException
from module_higgsfield.dao.generated_output_dao import GeneratedOutputDao
from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.dao.generation_read_dao import GenerationReadDao
from module_higgsfield.dao.usage_dao import UsageDao
from module_higgsfield.entity.vo.reference_vo import ReferenceInput
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.output_read_service import OutputReadService
from module_higgsfield.service.generation_target_service import GenerationTargetService
from module_higgsfield.service.task_billing_read_service import TaskBillingReadService
from module_higgsfield.service.generation_diagnostic_service import GenerationDiagnosticService


class GenerationReadService:
    @staticmethod
    async def source_job(db, user, job):
        """仅返回当前仍可读取的同项目来源，历史快照不替代实时授权。"""
        snapshot = job.input_snapshot
        source_id = snapshot.get('sourceJobId') if isinstance(snapshot, dict) else None
        if (not isinstance(source_id, str) or len(source_id) > 19
                or not source_id.isascii() or not source_id.isdecimal()):
            return None
        if not 0 < int(source_id) <= 9223372036854775807 or int(source_id) == job.job_id:
            return None
        source = await GenerationReadDao.job(db, int(source_id))
        if source is None or source.project_id != job.project_id:
            return None
        try:
            await WorkspaceService.authorize(
                db, user, source.project_id, 'generation:read', owner_id=source.actor_id
            )
        except PermissionException:
            return None
        return str(source.job_id)

    @staticmethod
    async def usage_state(db, job_id):
        """仅投影证据完整性；多次不同修订未经裁定，不能按到达顺序确认。"""
        rows = await UsageDao.job_evidence_states(db, job_id)
        if not any(state in {'available', 'partial'} for _, state in rows):
            return 'unknown'
        if all(state == 'available' for _, state in rows) and len({identity for identity, _ in rows}) == len(rows):
            return 'available'
        return 'partial'

    @classmethod
    async def snapshot(cls, db, user, identity):
        job = await GenerationReadDao.job(db, identity, lock=True)
        if job is None:
            WorkspaceService.conflict('RESOURCE_NOT_FOUND', '任务不存在或无权访问')
        _, _, allowed = await WorkspaceService.authorize(
            db, user, job.project_id, 'generation:read', owner_id=job.actor_id
        )
        model = await GenerationReadDao.model(db, job.model_version_id)
        if model is None:
            WorkspaceService.conflict('GENERATION_MODEL_UNAVAILABLE', '任务固定模型版本缺失，请联系管理员核查')
        summaries = await GeneratedOutputDao.archive_summaries(db, [job.job_id])
        output_rows = await GeneratedOutputDao.for_job(db, job.job_id)
        visible = 'asset:read' in allowed
        outputs = (
            [await OutputReadService.get(db, user, row.output_id) for row in output_rows if row.del_flag == '0']
            if visible
            else []
        )
        return {
            'id': str(job.job_id),
            'projectId': str(job.project_id),
            'sourceJobId': await cls.source_job(db, user, job),
            'diagnostic': await GenerationDiagnosticService.read(db, job),
            'elementDestination': await GenerationTargetService.project(db, user, job),
            'kind': job.kind,
            'createTime': job.create_time,
            'updateTime': job.update_time,
            'revision': str(job.revision),
            'model': {
                'id': str(model.model_id),
                'versionId': str(job.model_version_id),
                'displayName': model.display_name,
            },
            'orchestrationState': JobEventDao.ORCHESTRATION[int(job.orchestration_state)],
            'upstreamState': JobEventDao.UPSTREAM[int(job.upstream_state)],
            'archiveSummary': summaries[job.job_id],
            'billingState': ('pending', 'calculated', 'confirmed', 'disputed')[int(job.billing_state)],
            'usageState': await cls.usage_state(db, job.job_id),
            **await TaskBillingReadService.read(db, job, allowed),
            'outputs': outputs,
            'outputsVisibility': 'visible' if visible else 'hidden',
            'allowedActions': (
                ['generation:copy-input']
                if 'generation:create' in allowed and job.kind in {'image', 'video'}
                else []
            ) + (
                ['generation:cancel']
                if 'generation:cancel' in allowed
                and job.orchestration_state in {'0', '1'}
                and job.upstream_state == '0'
                and not job.upstream_task_id
                and not job.upstream_response_id
                else []
            ),
            'eventCursor': f'{job.job_id}:{job.event_sequence}',
            'cancelState': ('none', 'requested', 'confirmed', 'rejected', 'unsupported')[int(job.cancel_state)],
        }

    @classmethod
    async def list_context(cls, db, user, job, preview=None):
        """列表仅发布项目名称与平台金额摘要，不透传用量或采购证据。"""
        project, _, allowed = await WorkspaceService.authorize(
            db, user, job.project_id, 'generation:read', owner_id=job.actor_id
        )
        billing = await TaskBillingReadService.read(db, job, allowed)
        result = {'projectName': project.project_name, 'billingVisibility': billing['billingVisibility']}
        if preview and 'asset:read' in allowed:
            result['cardPreview'] = preview
        if billing['billingVisibility'] == 'visible':
            platform = billing['billing']['platform']
            result['billingSummary'] = {key: platform[key] for key in ('amount', 'currency', 'state')}
        return result

    @classmethod
    async def listing(cls, db, user, query):
        if '*:*:*' not in user.permissions and 'generation:read' not in user.permissions:
            raise PermissionException(message='没有读取生成任务的权限')
        if query.project_id:
            await WorkspaceService.authorize(db, user, int(query.project_id), 'project:read')
        rows, total = await GenerationReadDao.page(db, user.user.user_id, query)
        summaries = await GeneratedOutputDao.archive_summaries(db, [row.job_id for row in rows])
        previews = await GeneratedOutputDao.card_previews(db, [row.job_id for row in rows])
        return PageModel(
            rows=[
                {
                    'id': str(row.job_id),
                    'projectId': str(row.project_id),
                    'kind': row.kind,
                    'createTime': row.create_time,
                    'revision': str(row.revision),
                    'orchestrationState': JobEventDao.ORCHESTRATION[int(row.orchestration_state)],
                    'upstreamState': JobEventDao.UPSTREAM[int(row.upstream_state)],
                    'archiveSummary': summaries[row.job_id],
                    'billingState': ('pending', 'calculated', 'confirmed', 'disputed')[int(row.billing_state)],
                    # 列表不发布写动作；详情按最新任务状态及对象权限提供操作入口。
                    'allowedActions': [],
                    **await cls.list_context(db, user, row, previews.get(row.job_id)),
                }
                for row in rows
            ],
            total=total,
            pageNum=query.page_num,
            pageSize=query.page_size,
            hasNext=query.page_num * query.page_size < total,
        )

    @classmethod
    async def input(cls, db, user, identity):
        job = await GenerationReadDao.job(db, identity)
        if job is None:
            WorkspaceService.conflict('RESOURCE_NOT_FOUND', '任务不存在或无权访问')
        await WorkspaceService.authorize(db, user, job.project_id, 'generation:read', owner_id=job.actor_id)
        if job.kind not in {'image', 'video'}:
            WorkspaceService.conflict('GENERATION_INPUT_UNAVAILABLE', '对话上下文应通过已授权的会话接口读取')
        snapshot = job.input_snapshot
        try:
            # 引用键及多处来源存于输入快照，实际媒体必须匹配冻结引用表。
            content = ReferenceInput.model_validate(
                {
                    'prompt': snapshot['prompt'],
                    'references': snapshot['references'],
                }
            )
            references = await GenerationReadDao.references(db, identity)
            fixed = {
                (
                    str(row.asset_version_id),
                    str(row.element_revision_id) if row.element_revision_id else None,
                    row.media_role,
                )
                for row in references
                if not row.reference_snapshot.get('sources')
            }
            for row in references:
                for source in row.reference_snapshot.get('sources', []):
                    if source['assetVersionId'] != str(row.asset_version_id) or source['mediaRole'] != row.media_role:
                        raise ValueError('固定来源与媒体不一致')
                    fixed.add((source['assetVersionId'], source.get('elementRevisionId'), source['mediaRole']))
            requested = {(ref.asset_version_id, ref.element_revision_id, ref.media_role) for ref in content.references}
            if fixed != requested or not isinstance(snapshot['parameters'], dict):
                raise ValueError('固定输入不一致')
        except (KeyError, TypeError, ValueError, ValidationError):
            WorkspaceService.conflict('GENERATION_INPUT_UNAVAILABLE', '任务输入快照不完整，不能用于再次生成')
        return {
            'prompt': content.prompt.model_dump(by_alias=True),
            'parameters': snapshot['parameters'],
            'references': [ref.model_dump(by_alias=True) for ref in content.references],
            'modelVersionId': str(job.model_version_id),
            'createTime': job.create_time,
        }
