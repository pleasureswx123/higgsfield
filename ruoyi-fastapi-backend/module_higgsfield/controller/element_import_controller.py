"""元素文档导入受理和分页复核入口。"""
from typing import Annotated
from fastapi import Query, Request
from common.aspect.pre_auth import PreAuthDependency
from common.router import APIRouterPro
from module_higgsfield.controller.project_workspace_controller import Db, Key, OptionalKey, ProjectId, User, mutation_response
from module_higgsfield.entity.vo.element_import_vo import ElementImportCreate, ElementImportRowsQuery, ElementImportRowEdit, ElementImportConfirm
from module_higgsfield.service.element_import_service import ElementImportService
from module_higgsfield.service.element_import_edit_service import ElementImportEditService
from module_higgsfield.service.element_import_confirm_service import ElementImportConfirmService
from utils.response_util import ResponseUtil

element_import_controller = APIRouterPro(prefix='/api/v1/imports/elements', tags=['制作平台-元素导入'],
                                         order_num=84, dependencies=[PreAuthDependency()])


@element_import_controller.post('', summary='受理元素文档导入')
async def create_import(request: Request, payload: ElementImportCreate, key: Key, db: Db, user: User):
    return mutation_response(await ElementImportService.create(db, user, payload, key))


@element_import_controller.post('/{identity}/confirm', summary='原子确认选中候选为正式元素')
async def confirm_import(request: Request, identity: ProjectId, payload: ElementImportConfirm, key: Key, db: Db, user: User):
    return mutation_response(await ElementImportConfirmService.confirm(db, user, identity, payload, key))


@element_import_controller.get('/{identity}', summary='查看已授权导入批次摘要')
async def get_import(request: Request, identity: ProjectId, db: Db, user: User):
    return ResponseUtil.success(data=await ElementImportService.get(db, user, identity))


@element_import_controller.get('/{identity}/rows', summary='分页读取已授权导入候选')
async def get_rows(request: Request, identity: ProjectId, query: Annotated[ElementImportRowsQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await ElementImportService.rows(db, user, identity, query))


@element_import_controller.patch('/{identity}/rows/{row_no}', summary='复核候选字段和选中状态')
async def edit_row(request: Request, identity: ProjectId, row_no: ProjectId,
                   payload: ElementImportRowEdit, db: Db, user: User, key: OptionalKey = None):
    return mutation_response(await ElementImportEditService.edit(db, user, identity, row_no, payload, key))
