"""制作端发布能力投影，不返回供应商账号、别名及凭据内部信息。"""

from pydantic import ValidationError
from exceptions.exception import ServiceWarning
from common.vo import PageModel
from module_higgsfield.dao.model_catalog_dao import ModelCatalogDao
from module_higgsfield.entity.vo.model_capability_vo import ModelCapabilities
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.generation_policy_service import GenerationPolicyService


class ModelCatalogService:
    @staticmethod
    def runtime_ready():
        try:
            GenerationPolicyService.configured()
            GenerationPolicyService.tokens()
            return True
        except ServiceWarning:
            return False

    @staticmethod
    def availability(project, config, runtime_ready):
        # 目录没有完整输入，不能代替价格、预算、引用和凭据容量预检。
        if project.status != '0':
            reason = 'PROJECT_READ_ONLY'
        elif not runtime_ready:
            reason = 'GENERATION_POLICY_UNAVAILABLE'
        elif config.estimate_policy is None:
            reason = 'GENERATION_ESTIMATE_UNAVAILABLE'
        else:
            reason = 'GENERATION_PREFLIGHT_REQUIRED'
        return {'available': False, 'reasonCode': reason}

    @staticmethod
    def capability(version):
        try:
            return ModelCapabilities.model_validate(version.capabilities)
        except ValidationError:
            WorkspaceService.conflict('MODEL_CAPABILITY_INVALID', '模型能力配置无效，请联系管理员')

    @classmethod
    async def listing(cls, db, user, query):
        project, _, _ = await WorkspaceService.authorize(db, user, int(query.project_id), 'generation:create')
        rows, variants, total = await ModelCatalogDao.page(db, query)
        runtime_ready = cls.runtime_ready() if rows and project.status == '0' else False
        grouped = {}
        for variant in variants:
            grouped.setdefault(variant.model_version_id, []).append(
                {'id': str(variant.variant_id), 'dimensions': variant.dimensions}
            )
        values = []
        for model, version in rows:
            config = cls.capability(version)
            values.append(
                {
                    'id': str(model.model_id),
                    'versionId': str(version.model_version_id),
                    'displayName': model.display_name,
                    'kind': model.kind,
                    'menuMeta': config.presentation.model_dump(by_alias=True),
                    'parametersSchema': config.parameters_schema.model_dump(by_alias=True),
                    'referenceRules': config.reference_rules.model_dump(by_alias=True),
                    'defaultParameters': config.default_parameters,
                    'availableVariants': grouped.get(version.model_version_id, []),
                    'availability': cls.availability(project, config, runtime_ready),
                }
            )
        return PageModel(
            rows=values,
            total=total,
            pageNum=query.page_num,
            pageSize=query.page_size,
            hasNext=query.page_num * query.page_size < total,
        )

    @classmethod
    async def selected(cls, db, user, project_id, version_id, kind):
        await WorkspaceService.authorize(db, user, project_id, 'generation:create')
        row = await ModelCatalogDao.version(db, project_id, version_id)
        if row is None or row[0].kind != kind:
            WorkspaceService.conflict('MODEL_CAPABILITY_UNAVAILABLE', '模型版本未发布、未授权此项目或类型不匹配')
        return cls.capability(row[1])
