from typing import Annotated
from fastapi import Query, Request
from common.aspect.pre_auth import PreAuthDependency
from common.router import APIRouterPro
from module_higgsfield.controller.project_workspace_controller import Db, User
from module_higgsfield.entity.vo.cost_center_vo import CostCenterQuery
from module_higgsfield.service.cost_center_service import CostCenterService
from utils.response_util import ResponseUtil

cost_center_controller = APIRouterPro(prefix='/api/admin/v1/cost-centers', tags=['后台管理-管理成本中心'],
    order_num=98, dependencies=[PreAuthDependency()])


@cost_center_controller.get('', summary='读取可用管理成本中心')
async def listing(request: Request, query: Annotated[CostCenterQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await CostCenterService.listing(db, user, query))
