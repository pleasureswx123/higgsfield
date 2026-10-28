from fastapi import Request
from common.aspect.pre_auth import PreAuthDependency
from common.router import APIRouterPro
from module_higgsfield.controller.project_workspace_controller import Db, User, ProjectId, Key, mutation_response
from module_higgsfield.entity.vo.routing_vo import RoutingUpdate
from common.annotation.log_annotation import Log
from common.enums import BusinessType
from module_higgsfield.service.routing_service import RoutingService
from utils.response_util import ResponseUtil


routing_controller = APIRouterPro(
    prefix='/api/admin/v1', tags=['后台管理-项目模型路由'], order_num=90, dependencies=[PreAuthDependency()]
)


@routing_controller.get('/project-provider-configs/{project_id}', summary='读取治理范围内项目的整组模型路由')
async def get(request: Request, project_id: ProjectId, db: Db, user: User):
    return ResponseUtil.success(data=await RoutingService.get(db, user, project_id))


@routing_controller.put('/project-provider-configs/{project_id}', summary='原子替换项目模型路由整组配置')
@Log(title='配置项目模型路由', business_type=BusinessType.UPDATE)
async def save(request: Request, project_id: ProjectId, payload: RoutingUpdate, key: Key, db: Db, user: User):
    return mutation_response(await RoutingService.save(db, user, project_id, payload, key))
