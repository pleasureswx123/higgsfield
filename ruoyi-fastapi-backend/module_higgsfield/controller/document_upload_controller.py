"""管理文档独立入口，不开放原始存储路径。"""
from typing import Annotated
from fastapi import Header, Path, Request
from common.aspect.pre_auth import PreAuthDependency
from common.annotation.rate_limit_annotation import ApiRateLimit, ApiRateLimitPreset
from common.router import APIRouterPro
from module_higgsfield.controller.project_workspace_controller import Db, Key, ProjectId, User, mutation_response
from module_higgsfield.entity.vo.asset_vo import UploadComplete
from module_higgsfield.entity.vo.document_upload_vo import DocumentUploadCreate
from module_higgsfield.service.document_upload_service import DocumentUploadService
from utils.response_util import ResponseUtil

document_upload_controller = APIRouterPro(prefix='/api/admin/v1', tags=['后台管理-证据上传'],
    order_num=100, dependencies=[PreAuthDependency()])


@document_upload_controller.post('/document-uploads', summary='创建本人上传会话')
@ApiRateLimit(namespace='hf:document_create_upload', preset=ApiRateLimitPreset.USER_RESOURCE_UPLOAD)
async def create_upload(request: Request, payload: DocumentUploadCreate, key: Key, db: Db, user: User):
    return mutation_response(await DocumentUploadService.create(db, user, payload, key))


@document_upload_controller.get('/document-uploads/{upload_id}', summary='查询本人上传进度')
async def upload_status(request: Request, upload_id: ProjectId, db: Db, user: User):
    return ResponseUtil.success(data=await DocumentUploadService.get(db, user, upload_id))


@document_upload_controller.put(
    '/document-uploads/{upload_id}/parts/{part_no}',
    summary='上传并验证不可覆盖分片',
    openapi_extra={
        'requestBody': {
            'required': True,
            'content': {'application/octet-stream': {'schema': {'type': 'string', 'format': 'binary'}}},
        }
    },
)
@ApiRateLimit(namespace='hf:document_upload_part', preset=ApiRateLimitPreset.USER_RESOURCE_UPLOAD)
async def upload_part(
    request: Request,
    upload_id: ProjectId,
    part_no: Annotated[int, Path(ge=1)],
    db: Db,
    user: User,
    content_range: Annotated[str, Header(alias='Content-Range')],
    sha256: Annotated[str, Header(alias='X-Content-SHA256', pattern=r'^[a-f0-9]{64}$')],
):
    if request.headers.get('content-type', '').split(';')[0] != 'application/octet-stream':
        DocumentUploadService.fail('UPLOAD_CONTENT_TYPE_INVALID', '分片必须使用application/octet-stream')
    return ResponseUtil.success(
        data=await DocumentUploadService.put_part(db, user, upload_id, part_no, content_range, sha256, request.stream())
    )


@document_upload_controller.post('/document-uploads/{upload_id}/complete', summary='校验管理文档并归档')
@ApiRateLimit(namespace='hf:document_complete_upload', preset=ApiRateLimitPreset.USER_RESOURCE_UPLOAD)
async def complete_upload(
    request: Request, upload_id: ProjectId, payload: UploadComplete, key: Key, db: Db, user: User
):
    return mutation_response(await DocumentUploadService.complete(db, user, upload_id, payload, key))
