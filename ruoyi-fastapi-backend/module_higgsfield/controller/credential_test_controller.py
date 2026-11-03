from fastapi import Request, Query
from typing import Annotated
from common.aspect.pre_auth import PreAuthDependency
from common.annotation.log_annotation import Log
from common.enums import BusinessType
from common.router import APIRouterPro
from module_higgsfield.controller.project_workspace_controller import Db, User, Key, ProjectId, mutation_response
from module_higgsfield.entity.vo.credential_test_vo import CredentialTestCreate, CredentialTestPage
from module_higgsfield.service.credential_test_service import CredentialTestService
from module_higgsfield.service.credential_test_model_service import CredentialTestModelService
from utils.response_util import ResponseUtil
from module_higgsfield.controller.credential_route import CredentialRoute
from module_higgsfield.service.credential_test_detail_service import CredentialTestDetailService
from module_higgsfield.service.credential_test_runtime_service import CredentialTestRuntimeService
from module_higgsfield.service.admin_scope_service import AdminScopeService
from module_higgsfield.service.project_workspace_service import WorkspaceService

credential_test_controller = APIRouterPro(prefix='/api/admin/v1', tags=['后台管理-凭据测试'], order_num=99,
    dependencies=[PreAuthDependency()], route_class=CredentialRoute)


@credential_test_controller.get('/credential-test-runtime', summary='读取测试后台服务就绪状态')
async def runtime(request: Request, db: Db, user: User):
    await AdminScopeService.global_access(db, user, 'credential:read')
    return ResponseUtil.success(data=await CredentialTestRuntimeService.status(request.app.state.redis))


@credential_test_controller.get('/credential-tests/{test_id}/details', summary='只读查看脱敏请求和保存的响应')
async def details(request: Request, test_id: ProjectId, db: Db, user: User):
    return ResponseUtil.success(data=await CredentialTestDetailService.get(db, user, test_id))


@credential_test_controller.get('/credential-versions/{version_id}/test-preview', summary='只读预览测试请求，不调用供应商')
async def preview(request: Request, version_id: ProjectId, db: Db, user: User,
                  modelVersionId: Annotated[int, Query(gt=0, le=9223372036854775807)],
                  costCenterId: Annotated[int, Query(gt=0, le=9223372036854775807)]):
    return ResponseUtil.success(data=await CredentialTestDetailService.preview(db, user, version_id, modelVersionId, costCenterId))


@credential_test_controller.get('/credential-tests/{test_id}/video', summary='授权读取已归档的测试视频')
async def video(test_id: ProjectId, db: Db, user: User):
    return await CredentialTestDetailService.video(db, user, test_id)


@credential_test_controller.post('/credential-versions/{version_id}/tests', summary='受理凭据测试，不代表测试通过')
@Log(title='申请凭据测试', business_type=BusinessType.INSERT, request_log_mode='none', response_log_mode='none')
async def create(request: Request, version_id: ProjectId, payload: CredentialTestCreate, key: Key, db: Db, user: User):
    await AdminScopeService.global_access(db, user, 'credential:test')
    if not (await CredentialTestRuntimeService.status(request.app.state.redis))['ready']:
        WorkspaceService.conflict('TEST_SERVICE_UNAVAILABLE', '测试服务暂未就绪，请稍后刷新或联系平台维护人员；本次没有发起供应商调用')
    return mutation_response(await CredentialTestService.create(db, user, version_id, payload, key))


@credential_test_controller.get('/credential-tests/{test_id}', summary='读取凭据测试状态')
async def get(request: Request, test_id: ProjectId, db: Db, user: User):
    return ResponseUtil.success(data=await CredentialTestService.get(db, user, test_id))


@credential_test_controller.get('/credential-versions/{version_id}/tests', summary='分页读取当前凭据版本的测试历史')
async def listing(request: Request, version_id: ProjectId, query: Annotated[CredentialTestPage, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await CredentialTestService.listing(db, user, version_id, query))


@credential_test_controller.get('/credential-versions/{version_id}/test-models', summary='分页读取同连接区域的图片测试候选')
async def models(request: Request, version_id: ProjectId, query: Annotated[CredentialTestPage, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await CredentialTestModelService.listing(db, user, version_id, query))
