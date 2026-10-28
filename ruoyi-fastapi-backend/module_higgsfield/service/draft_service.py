"""草稿始终本人私有，保存不计费也不调用供应商。"""

from common.vo import PageModel

from module_higgsfield.dao.draft_dao import DraftDao
from module_higgsfield.dao.generation_read_dao import GenerationReadDao
from module_higgsfield.dao.folder_dao import FolderDao
from module_higgsfield.entity.vo.reference_vo import ReferenceInput
from module_higgsfield.service.element_service import ElementService
from module_higgsfield.service.folder_service import FolderService
from module_higgsfield.service.reference_compile_service import ReferenceCompileService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService
from module_higgsfield.service.model_catalog_service import ModelCatalogService
from module_higgsfield.service.model_capability_service import ModelCapabilityService


class DraftService:
    fail = staticmethod(WorkspaceService.conflict)

    @classmethod
    async def listing(cls, db, user, query):
        await WorkspaceService.authorize(db, user, int(query.project_id), 'project:read')
        rows, total = await DraftDao.page(db, user.user.user_id, query)
        summaries = []
        for row in rows:
            excerpt = '\n'.join(
                ''.join(
                    node.get('text', '') if node.get('type') == 'text' else '[引用]'
                    for node in paragraph.get('content', [])
                )
                for paragraph in row.body.get('prompt', {}).get('content', [])
            )
            summaries.append(
                {
                    'id': str(row.draft_id),
                    'projectId': str(row.project_id),
                    'kind': row.kind,
                    'revision': str(row.revision),
                    'updateTime': row.update_time,
                    'promptExcerpt': excerpt[:160],
                    'modelVersionId': row.body.get('modelVersionId'),
                }
            )
        return PageModel(
            rows=summaries,
            total=total,
            pageNum=query.page_num,
            pageSize=query.page_size,
            hasNext=query.page_num * query.page_size < total,
        )

    @classmethod
    async def owned(cls, db, user, draft_id):
        draft = await DraftDao.get(db, draft_id)
        if draft is None or draft.owner_id != user.user.user_id:
            cls.fail('RESOURCE_NOT_FOUND', '草稿不存在或不属于当前用户')
        return draft

    @staticmethod
    async def result(db, draft):
        rows = await DraftDao.references(db, draft.draft_id)
        return {
            'id': str(draft.draft_id),
            'projectId': str(draft.project_id),
            'kind': draft.kind,
            'body': draft.body,
            'revision': str(draft.revision),
            'updateTime': draft.update_time,
            'references': [
                {
                    'referenceKey': str(row.reference_key),
                    'assetVersionId': str(row.asset_version_id),
                    'elementRevisionId': str(row.element_revision_id) if row.element_revision_id else None,
                    'mediaRole': row.media_role,
                    'ordinal': row.ordinal,
                }
                for row in rows
            ],
        }

    @classmethod
    async def get(cls, db, user, draft_id):
        draft = await cls.owned(db, user, draft_id)
        await WorkspaceService.authorize(db, user, draft.project_id, 'project:read')
        return await cls.result(db, draft)

    @classmethod
    async def validate(cls, db, user, project_id, payload, kind):
        body = payload.body
        if body.source_job_id:
            source = await GenerationReadDao.job(db, int(body.source_job_id))
            if source is None or source.project_id != project_id:
                cls.fail('RESOURCE_NOT_FOUND', '来源任务不存在或无权访问')
            await WorkspaceService.authorize(db, user, project_id, 'generation:read', owner_id=source.actor_id)
        capabilities = None
        roles = {'reference_image': ['image'], 'first_frame': ['image'], 'reference_video': ['video']}
        if body.model_version_id is not None:
            capabilities = await ModelCatalogService.selected(db, user, project_id, int(body.model_version_id), kind)
            ModelCapabilityService.parameters(capabilities, body.parameters, require_complete=False)
            roles = {name: rule.media_types for name, rule in capabilities.reference_rules.roles.items()}
        # 未绑定模型的私有草稿允许保留待配置参数；实际生成仍由提交链校验模型授权和参数。
        space = await FolderDao.space(db, project_id)
        await FolderService.check_target(db, space.space_id, int(body.folder_id) if body.folder_id else None, 'media')
        if body.target_element_id:
            _, project, _ = await ElementService.authorized(db, user, int(body.target_element_id), 'element:edit')
            if project.project_id != project_id:
                cls.fail('REFERENCE_UNAVAILABLE', '回填元素必须属于当前项目')
        if body.return_context and (
            body.return_context.project_id != str(project_id)
            or body.return_context.element_id != body.target_element_id
        ):
            cls.fail('RETURN_CONTEXT_INVALID', '回填上下文必须与项目及目标元素一致')
        compiled = await ReferenceCompileService.resolve(
            db,
            user,
            project_id,
            ReferenceInput(prompt=body.prompt, references=payload.references),
            roles,
        )
        if capabilities is not None:
            ModelCapabilityService.references(capabilities, compiled, require_complete=False)

    @classmethod
    async def save(cls, db, user, payload, key, draft_id=None):
        path, method = ('/drafts', 'POST') if draft_id is None else (f'/drafts/{draft_id}', 'PUT')
        data = payload.model_dump(by_alias=True)
        try:
            await WriteService.lock(db, user, path, key)
            draft = await cls.owned(db, user, draft_id) if draft_id is not None else None
            project_id = draft.project_id if draft else int(payload.project_id)
            await WorkspaceService.authorize(db, user, project_id, 'generation:create', write=True)
            replay = await WriteService.replay(db, user, path, key, data, method)
            if replay:
                await db.commit()
                return replay, True
            if draft:
                draft = await cls.owned(db, user, draft_id)
                WorkspaceService.check_revision(draft, payload.revision)
            await cls.validate(db, user, project_id, payload, draft.kind if draft else payload.kind)
            audit = WriteService.audit(user)
            if draft is None:
                draft = await DraftDao.add(
                    db,
                    project_id=project_id,
                    owner_id=user.user.user_id,
                    kind=payload.kind,
                    body=payload.body.model_dump(by_alias=True),
                    schema_version=1,
                    revision=1,
                    **audit,
                )
            else:
                draft.body = payload.body.model_dump(by_alias=True)
                draft.revision += 1
                draft.update_by, draft.update_time = audit['update_by'], audit['update_time']
            await DraftDao.replace_references(db, draft.draft_id, payload.references, audit)
            return await WriteService.finish(
                db, user, path, key, data, await cls.result(db, draft), 'draft', draft.draft_id, method
            )
        except Exception:
            await db.rollback()
            raise
