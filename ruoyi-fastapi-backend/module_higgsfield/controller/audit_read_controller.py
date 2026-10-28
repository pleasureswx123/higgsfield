from typing import Annotated
from fastapi import Query, Request
from common.aspect.pre_auth import PreAuthDependency
from common.router import APIRouterPro
from module_higgsfield.controller.project_workspace_controller import Db, User
from module_higgsfield.entity.vo.audit_query_vo import AuditQuery
from module_higgsfield.service.audit_read_service import AuditReadService
from utils.response_util import ResponseUtil

audit_read_controller = APIRouterPro(
    prefix='/api/admin/v1/audit-logs', tags=['后台管理-业务审计'], order_num=95,
    dependencies=[PreAuthDependency()],
)


@audit_read_controller.get('', summary='分页读取管理范围内的业务审计')
async def listing(request: Request, query: Annotated[AuditQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await AuditReadService.listing(db, user, query))
