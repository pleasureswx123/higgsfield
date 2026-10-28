"""个人收藏入口；不增加内容授权，不允许操作其他用户的关系。"""
from typing import Annotated
from fastapi import Query, Request
from common.aspect.pre_auth import PreAuthDependency
from common.router import APIRouterPro
from module_higgsfield.controller.project_workspace_controller import Db, User, OptionalKey, ProjectId, mutation_response
from module_higgsfield.entity.vo.favorite_vo import FavoriteCreate, FavoriteQuery
from module_higgsfield.service.favorite_service import FavoriteService
from utils.response_util import ResponseUtil

favorite_controller = APIRouterPro(prefix='/api/v1/favorites', tags=['制作平台-个人收藏'],
                                    order_num=85, dependencies=[PreAuthDependency()])


@favorite_controller.post('', summary='收藏当前可读对象')
async def create_favorite(request: Request, payload: FavoriteCreate, db: Db, user: User, key: OptionalKey = None):
    return mutation_response(await FavoriteService.create(db, user, payload, key))


@favorite_controller.get('', summary='分页读取本人的收藏并重新核验来源')
async def list_favorites(request: Request, query: Annotated[FavoriteQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await FavoriteService.listing(db, user, query))


@favorite_controller.delete('/{identity}', summary='取消本人的收藏')
async def cancel_favorite(request: Request, identity: ProjectId, db: Db, user: User, key: OptionalKey = None):
    return mutation_response(await FavoriteService.cancel(db, user, identity, key))
