from typing import Annotated
from fastapi import Query, Request
from common.aspect.pre_auth import PreAuthDependency
from common.annotation.log_annotation import Log
from common.enums import BusinessType
from common.router import APIRouterPro
from module_higgsfield.controller.project_workspace_controller import Db, User, Key, ProjectId, mutation_response
from module_higgsfield.entity.vo.model_vo import ModelCreate, ModelVersionCreate, ModelVariantCreate, ModelQuery
from module_higgsfield.service.model_admin_service import ModelAdminService
from module_higgsfield.entity.vo.model_vo import ModelVersionPatch, ModelVersionAction, ModelVersionVerify
from utils.response_util import ResponseUtil

model_admin_controller = APIRouterPro(
    prefix='/api/admin/v1', tags=['后台管理-模型能力'], order_num=87, dependencies=[PreAuthDependency()]
)
PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


@model_admin_controller.get('/model-profiles', summary='分页读取后台模型身份')
async def models(request: Request, query: Annotated[ModelQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(
        model_content=await ModelAdminService.listing(
            db, user, 'models', page_num=query.page_num, page_size=query.page_size, query=query
        )
    )


@model_admin_controller.post('/model-profiles', summary='登记模型身份')
@Log(title='登记模型身份', business_type=BusinessType.INSERT)
async def create_model(request: Request, payload: ModelCreate, key: Key, db: Db, user: User):
    return mutation_response(await ModelAdminService.create(db, user, 'model', payload, key))


@model_admin_controller.get('/model-profiles/{model_id}/versions', summary='读取能力版本列表')
async def versions(
    request: Request, model_id: ProjectId, db: Db, user: User, pageNum: PageNumber = 1, pageSize: PageSize = 30
):
    return ResponseUtil.success(
        model_content=await ModelAdminService.listing(db, user, 'versions', model_id, pageNum, pageSize)
    )


@model_admin_controller.post('/model-profiles/{model_id}/versions', summary='新增草稿能力版本')
@Log(title='新增模型能力版本', business_type=BusinessType.INSERT)
async def create_version(
    request: Request, model_id: ProjectId, payload: ModelVersionCreate, key: Key, db: Db, user: User
):
    return mutation_response(await ModelAdminService.create(db, user, 'version', payload, key, model_id))


@model_admin_controller.get('/model-profile-versions/{version_id}', summary='读取后台能力版本详情')
async def version(request: Request, version_id: ProjectId, db: Db, user: User):
    return ResponseUtil.success(data=await ModelAdminService.get(db, user, version_id))


@model_admin_controller.get('/model-profile-versions/{version_id}/variants', summary='读取精确计价规格')
async def variants(
    request: Request, version_id: ProjectId, db: Db, user: User, pageNum: PageNumber = 1, pageSize: PageSize = 30
):
    return ResponseUtil.success(
        model_content=await ModelAdminService.listing(db, user, 'variants', version_id, pageNum, pageSize)
    )


@model_admin_controller.post('/model-profile-versions/{version_id}/variants', summary='登记完整精确规格')
@Log(title='登记模型精确规格', business_type=BusinessType.INSERT)
async def create_variant(
    request: Request, version_id: ProjectId, payload: ModelVariantCreate, key: Key, db: Db, user: User
):
    return mutation_response(await ModelAdminService.create(db, user, 'variant', payload, key, version_id))


@model_admin_controller.patch('/model-profile-versions/{version_id}', summary='编辑草稿能力版本')
@Log(title='编辑模型能力版本', business_type=BusinessType.UPDATE)
async def edit_version(
    request: Request, version_id: ProjectId, payload: ModelVersionPatch, key: Key, db: Db, user: User
):
    return mutation_response(await ModelAdminService.mutate(db, user, version_id, 'edit', payload, key))


@model_admin_controller.post('/model-profile-versions/{version_id}/verify', summary='登记已审阅的模型联调证据')
@Log(title='登记模型验证证据', business_type=BusinessType.UPDATE)
async def verify_version(
    request: Request, version_id: ProjectId, payload: ModelVersionVerify, key: Key, db: Db, user: User
):
    return mutation_response(await ModelAdminService.mutate(db, user, version_id, 'verify', payload, key))


@model_admin_controller.post('/model-profile-versions/{version_id}/publish', summary='发布已验证模型能力')
@Log(title='发布模型能力版本', business_type=BusinessType.UPDATE)
async def publish_version(
    request: Request, version_id: ProjectId, payload: ModelVersionAction, key: Key, db: Db, user: User
):
    return mutation_response(await ModelAdminService.mutate(db, user, version_id, 'publish', payload, key))


@model_admin_controller.post('/model-profile-versions/{version_id}/disable', summary='停用模型能力版本')
@Log(title='停用模型能力版本', business_type=BusinessType.UPDATE)
async def disable_version(
    request: Request, version_id: ProjectId, payload: ModelVersionAction, key: Key, db: Db, user: User
):
    return mutation_response(await ModelAdminService.mutate(db, user, version_id, 'disable', payload, key))
