from typing import Annotated
from fastapi import Query, Request
from common.aspect.pre_auth import PreAuthDependency
from common.router import APIRouterPro
from module_higgsfield.controller.project_workspace_controller import Db, User
from module_higgsfield.entity.vo.model_catalog_vo import ModelCatalogQuery
from module_higgsfield.service.model_catalog_service import ModelCatalogService
from utils.response_util import ResponseUtil


model_catalog_controller = APIRouterPro(
    prefix='/api/v1', tags=['制作平台-项目模型目录'], order_num=91, dependencies=[PreAuthDependency()]
)


@model_catalog_controller.get('/model-profiles', summary='分页读取项目已授权发布的模型能力')
async def listing(request: Request, query: Annotated[ModelCatalogQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await ModelCatalogService.listing(db, user, query))
