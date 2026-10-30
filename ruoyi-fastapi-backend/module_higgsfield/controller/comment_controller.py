"""固定媒体评论入口，复用平台认证、分页及幂等协议。"""
from typing import Annotated
from fastapi import Query, Request
from common.router import APIRouterPro
from common.aspect.pre_auth import PreAuthDependency
from module_higgsfield.controller.project_workspace_controller import Db, User, Key, ProjectId, mutation_response
from module_higgsfield.entity.vo.comment_vo import ThreadCreate, ThreadQuery, CommentCreate, CommentPage, CommentPatch, CommentDelete, ThreadPatch, ReactionPatch
from module_higgsfield.service.comment_service import CommentService as Service
from utils.response_util import ResponseUtil

comment_controller = APIRouterPro(prefix='/api/v1', tags=['制作平台-评论协作'], order_num=86,
                                 dependencies=[PreAuthDependency()])


@comment_controller.post('/comment-threads', summary='创建固定版本评论主题')
async def create_thread(request: Request, payload: ThreadCreate, key: Key, db: Db, user: User):
    return mutation_response(await Service.create_thread(db, user, payload, key))


@comment_controller.get('/comment-threads', summary='分页读取授权目标评论主题')
async def threads(request: Request, query: Annotated[ThreadQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await Service.threads(db, user, query))


@comment_controller.get('/comment-threads/{identity}/comments', summary='读取主题内评论与回复')
async def comments(request: Request, identity: ProjectId, query: Annotated[CommentPage, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await Service.comments(db, user, identity, query))


@comment_controller.post('/comment-threads/{identity}/comments', summary='发表评论或同主题回复')
async def create_comment(request: Request, identity: ProjectId, payload: CommentCreate, key: Key, db: Db, user: User):
    return mutation_response(await Service.create_comment(db, user, identity, payload, key))


@comment_controller.patch('/comments/{identity}', summary='作者或治理人员原子更新评论与标注')
async def edit_comment(request: Request, identity: ProjectId, payload: CommentPatch, key: Key, db: Db, user: User):
    return mutation_response(await Service.mutate(db, user, identity, payload, key))


@comment_controller.delete('/comments/{identity}', summary='作者或治理人员逻辑删除评论并保留回复')
async def delete_comment(request: Request, identity: ProjectId, query: Annotated[CommentDelete, Query()], key: Key, db: Db, user: User):
    return mutation_response(await Service.mutate(db, user, identity, query, key, delete=True))


@comment_controller.patch('/comment-threads/{identity}', summary='解决、重开或逻辑删除讨论')
async def update_thread(request: Request, identity: ProjectId, payload: ThreadPatch, key: Key, db: Db, user: User):
    return mutation_response(await Service.collaborate(db, user, identity, payload, key))


@comment_controller.patch('/comments/{identity}/reaction', summary='设置当前用户的表情回应')
async def update_reaction(request: Request, identity: ProjectId, payload: ReactionPatch, key: Key, db: Db, user: User):
    return mutation_response(await Service.collaborate(db, user, identity, payload, key, reaction=True))
