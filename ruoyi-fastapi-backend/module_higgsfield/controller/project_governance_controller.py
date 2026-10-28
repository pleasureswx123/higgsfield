from typing import Annotated
from fastapi import Request, Query
from common.aspect.pre_auth import PreAuthDependency
from common.router import APIRouterPro
from common.annotation.log_annotation import Log
from common.enums import BusinessType
from module_higgsfield.controller.project_workspace_controller import Db, User, ProjectId, Key, mutation_response
from module_higgsfield.entity.vo.project_governance_vo import ProjectGovernanceAction, ProjectGovernanceQuery
from utils.response_util import ResponseUtil
from module_higgsfield.service.project_governance_service import ProjectGovernanceService

project_governance_controller = APIRouterPro(
    prefix='/api/admin/v1', tags=['后台管理-项目治理'], order_num=94, dependencies=[PreAuthDependency()]
)


@project_governance_controller.get('/projects', summary='分页读取治理范围内的项目元数据')
async def listing(request: Request, query: Annotated[ProjectGovernanceQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await ProjectGovernanceService.listing(db, user, query))


@project_governance_controller.post('/projects/{project_id}/governance', summary='治理范围内暂停、恢复及归档项目')
@Log(title='项目治理', business_type=BusinessType.UPDATE)
async def governance(request: Request, project_id: ProjectId, payload: ProjectGovernanceAction, key: Key, db: Db, user: User):
    return mutation_response(await ProjectGovernanceService.change(db, user, project_id, payload, key))
