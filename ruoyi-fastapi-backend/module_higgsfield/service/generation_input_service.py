"""受理短事务内准备固定输入，不提交事务、不预占或调用供应商。"""

from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.vo.user_vo import CurrentUserModel
from module_higgsfield.dao.draft_dao import DraftDao
from module_higgsfield.dao.folder_dao import FolderDao
from module_higgsfield.dao.generation_read_dao import GenerationReadDao
from module_higgsfield.dao.model_catalog_dao import ModelCatalogDao
from module_higgsfield.dao.model_dao import ModelDao
from module_higgsfield.entity.do.model_do import HfModelVariant
from module_higgsfield.entity.vo.generation_input_vo import GenerationInput
from module_higgsfield.entity.vo.model_capability_vo import ModelCapabilities, scalar_equal
from module_higgsfield.service.folder_service import FolderService
from module_higgsfield.service.generation_target_service import GenerationTargetService
from module_higgsfield.service.model_capability_service import ModelCapabilityService
from module_higgsfield.service.model_catalog_service import ModelCatalogService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.reference_compile_service import ReferenceCompileService
from module_higgsfield.service.write_service import WriteService


class GenerationInputService:
    @staticmethod
    def select_variant(
        capabilities: ModelCapabilities, parameters: dict, variants: list[HfModelVariant]
    ) -> HfModelVariant:
        dimensions = capabilities.variant_dimensions
        if any(name not in parameters or not rule.accepts(parameters[name]) for name, rule in dimensions.items()):
            WorkspaceService.conflict('MODEL_VARIANT_UNAVAILABLE', '生成参数缺少合法的计价规格维度')
        matched = [
            row
            for row in variants
            if set(row.dimensions) == set(dimensions)
            and all(scalar_equal(row.dimensions[name], parameters[name]) for name in dimensions)
        ]
        if len(matched) != 1:
            WorkspaceService.conflict('MODEL_VARIANT_UNAVAILABLE', '生成参数无法唯一匹配已发布计价规格')
        return matched[0]

    @classmethod
    async def prepare(cls, db: AsyncSession, user: CurrentUserModel, payload: GenerationInput) -> dict:
        project_id = int(payload.project_id)
        await WorkspaceService.authorize(db, user, project_id, 'generation:create', write=True)
        if payload.target_element_id:
            await GenerationTargetService.validate(db, user, project_id, payload.target_element_id)
        if payload.draft_id:
            draft = await DraftDao.get(db, int(payload.draft_id))
            if draft is None or draft.owner_id != user.user.user_id or draft.project_id != project_id:
                WorkspaceService.conflict('RESOURCE_NOT_FOUND', '草稿不存在或无权访问')
            WorkspaceService.check_revision(draft, payload.draft_revision)
            references = await DraftDao.references(db, draft.draft_id)
            saved = [
                {
                    'referenceKey': str(row.reference_key),
                    'assetVersionId': str(row.asset_version_id),
                    'elementRevisionId': str(row.element_revision_id) if row.element_revision_id else None,
                    'mediaRole': row.media_role,
                    'ordinal': row.ordinal,
                }
                for row in references
            ]
            expected = {
                key: draft.body.get(key)
                for key in ('prompt', 'parameters', 'modelVersionId', 'folderId', 'sourceJobId')
            }
            actual = payload.model_dump(
                by_alias=True, include={'prompt', 'parameters', 'model_version_id', 'folder_id', 'source_job_id'}
            )
            if (
                draft.kind != payload.kind
                or WriteService.digest(expected) != WriteService.digest(actual)
                or WriteService.digest(saved)
                != WriteService.digest(
                    [row.model_dump(by_alias=True) for row in sorted(payload.references, key=lambda row: row.ordinal)]
                )
            ):
                WorkspaceService.conflict('DRAFT_INPUT_MISMATCH', '提交内容与草稿修订不一致，请先保存草稿')
        if payload.source_job_id:
            source = await GenerationReadDao.job(db, int(payload.source_job_id))
            if source is None or source.project_id != project_id:
                WorkspaceService.conflict('RESOURCE_NOT_FOUND', '来源任务不存在或无权访问')
            await WorkspaceService.authorize(db, user, project_id, 'generation:read', owner_id=source.actor_id)
        row = await ModelCatalogDao.version(db, project_id, int(payload.model_version_id))
        if row is None or row[0].kind != payload.kind:
            WorkspaceService.conflict('MODEL_CAPABILITY_UNAVAILABLE', '模型版本未发布、未授权此项目或类型不匹配')
        capabilities = ModelCatalogService.capability(row[1])
        parameters = ModelCapabilityService.parameters(capabilities, payload.parameters)
        variant = cls.select_variant(capabilities, parameters, await ModelDao.variants(db, row[1].model_version_id))
        space = await FolderDao.space(db, project_id)
        await FolderService.check_target(
            db, space.space_id, int(payload.folder_id) if payload.folder_id else None, 'media'
        )
        compiled = await ReferenceCompileService.resolve(
            db,
            user,
            project_id,
            payload,
            {name: rule.media_types for name, rule in capabilities.reference_rules.roles.items()},
        )
        ModelCapabilityService.references(capabilities, compiled)
        return {
            'modelVersionId': str(row[1].model_version_id),
            'modelVariantId': str(variant.variant_id),
            'inputSnapshot': {
                **({'targetElementId': payload.target_element_id} if payload.target_element_id else {}),
                'prompt': payload.prompt.model_dump(by_alias=True),
                'parameters': parameters,
                'references': [item.model_dump(by_alias=True) for item in payload.references],
                'folderId': payload.folder_id,
                'sourceJobId': payload.source_job_id,
                'draftId': payload.draft_id,
                'draftRevision': payload.draft_revision,
                'compiled': compiled,
            },
        }
