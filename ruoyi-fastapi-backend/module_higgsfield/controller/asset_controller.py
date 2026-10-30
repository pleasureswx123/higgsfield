from typing import Annotated

from fastapi import Header, Path, Query, Request, Response

from common.aspect.pre_auth import PreAuthDependency
from common.annotation.log_annotation import Log
from common.annotation.rate_limit_annotation import ApiRateLimit, ApiRateLimitPreset
from common.enums import BusinessType
from common.router import APIRouterPro
from module_higgsfield.controller.project_workspace_controller import Db, Key, ProjectId, User, mutation_response
from module_higgsfield.entity.vo.asset_vo import (
    AssetCreate,
    AssetAction,
    AssetPatch,
    AssetStatus,
    AssetVersionCreate,
    LibraryMove,
    LibraryQuery,
    UploadComplete,
    UploadCreate,
)
from module_higgsfield.service.asset_service import AssetService
from module_higgsfield.service.asset_lifecycle_service import AssetLifecycleService
from module_higgsfield.service.upload_service import UploadService
from utils.response_util import ResponseUtil

asset_controller = APIRouterPro(
    prefix='/api/v1', tags=['制作平台-上传与素材'], order_num=83, dependencies=[PreAuthDependency()]
)


@asset_controller.get('/projects/{project_id}/library', summary='分页读取当前目录素材')
async def library(request: Request, project_id: ProjectId, query: Annotated[LibraryQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await AssetService.library(db, user, project_id, query))


@asset_controller.post('/projects/{project_id}/library/move', summary='移动素材目录归属')
@Log(title='移动素材目录归属', business_type=BusinessType.UPDATE)
async def move_entry(request: Request, project_id: ProjectId, payload: LibraryMove, key: Key, db: Db, user: User):
    return mutation_response(await AssetService.move(db, user, project_id, payload, key))


@asset_controller.post('/projects/{project_id}/library/copy', summary='复制素材到目标目录')
@Log(title='复制素材到目标目录', business_type=BusinessType.INSERT)
async def copy_entry(request: Request, project_id: ProjectId, payload: LibraryMove, key: Key, db: Db, user: User):
    return mutation_response(await AssetService.move(db, user, project_id, payload, key, copy=True))


@asset_controller.patch('/assets/{asset_id}/status', summary='修改素材工作状态')
@Log(title='修改素材工作状态', business_type=BusinessType.UPDATE)
async def asset_status(request: Request, asset_id: ProjectId, payload: AssetStatus, key: Key, db: Db, user: User):
    return mutation_response(await AssetLifecycleService.mutate(db, user, asset_id, 'status', payload, key))


@asset_controller.get('/asset-versions/{version_id}/document-text', summary='授权文档纯文本预览')
async def document_text(request: Request, version_id: ProjectId, db: Db, user: User):
    return ResponseUtil.success(data=await AssetService.document_text(db, user, version_id),
                                headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})


@asset_controller.get('/asset-versions/{version_id}/thumbnail', summary='授权读取素材图片缩略图')
@asset_controller.head('/asset-versions/{version_id}/thumbnail', summary='授权读取素材缩略图元数据')
async def thumbnail(request: Request, version_id: ProjectId, db: Db, user: User):
    stream, headers, mime, status = await AssetService.media(
        db, user, version_id, request.headers.get('range'), head=request.method == 'HEAD', thumbnail=True
    )
    if request.method == 'HEAD':
        return Response(headers=headers, media_type=mime, status_code=status)
    return ResponseUtil.streaming(data=stream, headers=headers, media_type=mime, status_code=status)


@asset_controller.get('/asset-versions/{version_id}/preview', summary='授权媒体预览')
@asset_controller.head('/asset-versions/{version_id}/preview', summary='授权预览元数据')
async def preview(request: Request, version_id: ProjectId, db: Db, user: User):
    stream, headers, mime, status = await AssetService.media(
        db, user, version_id, request.headers.get('range'), head=request.method == 'HEAD'
    )
    if request.method == 'HEAD':
        return Response(headers=headers, media_type=mime, status_code=status)
    return ResponseUtil.streaming(data=stream, headers=headers, media_type=mime, status_code=status)


@asset_controller.get('/asset-versions/{version_id}/download', summary='授权媒体下载')
@asset_controller.head('/asset-versions/{version_id}/download', summary='授权下载元数据')
async def download(request: Request, version_id: ProjectId, db: Db, user: User):
    stream, headers, mime, status = await AssetService.media(
        db, user, version_id, request.headers.get('range'), download=True, head=request.method == 'HEAD'
    )
    if request.method == 'HEAD':
        return Response(headers=headers, media_type=mime, status_code=status)
    return ResponseUtil.streaming(data=stream, headers=headers, media_type=mime, status_code=status)


@asset_controller.post('/uploads', summary='创建本人上传会话')
@ApiRateLimit(namespace='hf:create_upload', preset=ApiRateLimitPreset.USER_RESOURCE_UPLOAD)
async def create_upload(request: Request, payload: UploadCreate, key: Key, db: Db, user: User):
    return mutation_response(await UploadService.create(db, user, payload, key))


@asset_controller.get('/uploads/{upload_id}', summary='查询本人上传进度')
async def upload_status(request: Request, upload_id: ProjectId, db: Db, user: User):
    return ResponseUtil.success(data=await UploadService.get(db, user, upload_id))


@asset_controller.put(
    '/uploads/{upload_id}/parts/{part_no}',
    summary='上传并验证不可覆盖分片',
    openapi_extra={
        'requestBody': {
            'required': True,
            'content': {'application/octet-stream': {'schema': {'type': 'string', 'format': 'binary'}}},
        }
    },
)
@ApiRateLimit(namespace='hf:upload_part', preset=ApiRateLimitPreset.USER_RESOURCE_UPLOAD)
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
        UploadService.fail('UPLOAD_CONTENT_TYPE_INVALID', '分片必须使用application/octet-stream')
    return ResponseUtil.success(
        data=await UploadService.put_part(db, user, upload_id, part_no, content_range, sha256, request.stream())
    )


@asset_controller.post('/uploads/{upload_id}/complete', summary='校验完整媒体并归档')
@ApiRateLimit(namespace='hf:complete_upload', preset=ApiRateLimitPreset.USER_RESOURCE_UPLOAD)
async def complete_upload(
    request: Request, upload_id: ProjectId, payload: UploadComplete, key: Key, db: Db, user: User
):
    return mutation_response(await UploadService.complete(db, user, upload_id, payload, key))


@asset_controller.delete('/uploads/{upload_id}', summary='取消未绑定上传')
async def cancel_upload(request: Request, upload_id: ProjectId, db: Db, user: User):
    await UploadService.cancel(db, user, upload_id)
    return ResponseUtil.success()


@asset_controller.post('/assets', summary='将上传原子绑定为素材')
@Log(title='创建项目素材', business_type=BusinessType.INSERT)
async def create_asset(request: Request, payload: AssetCreate, key: Key, db: Db, user: User):
    return mutation_response(await AssetService.bind(db, user, payload, key))


@asset_controller.post('/assets/{asset_id}/versions', summary='追加素材不可变版本')
@Log(title='追加素材版本', business_type=BusinessType.INSERT)
async def add_version(request: Request, asset_id: ProjectId, payload: AssetVersionCreate, key: Key, db: Db, user: User):
    return mutation_response(await AssetService.bind(db, user, payload, key, asset_id=asset_id))


@asset_controller.get('/asset-versions/{version_id}', summary='读取授权素材固定版本详情')
async def asset_version_detail(request: Request, version_id: ProjectId, db: Db, user: User):
    return ResponseUtil.success(data=await AssetService.get_version(db, user, version_id))


@asset_controller.get('/assets/{asset_id}', summary='读取授权素材详情')
async def asset_detail(request: Request, asset_id: ProjectId, db: Db, user: User):
    return ResponseUtil.success(data=await AssetService.get(db, user, asset_id))


@asset_controller.patch('/assets/{asset_id}', summary='重命名素材身份')
@Log(title='重命名项目素材', business_type=BusinessType.UPDATE)
async def rename_asset(request: Request, asset_id: ProjectId, payload: AssetPatch, key: Key, db: Db, user: User):
    return mutation_response(await AssetLifecycleService.mutate(db, user, asset_id, 'rename', payload, key))


@asset_controller.delete('/assets/{asset_id}', summary='逻辑删除素材并保留历史文件')
@Log(title='删除项目素材', business_type=BusinessType.DELETE)
async def remove_asset(
    request: Request,
    asset_id: ProjectId,
    query: Annotated[AssetAction, Query()],
    key: Key,
    db: Db,
    user: User,
):
    return mutation_response(
        await AssetLifecycleService.mutate(db, user, asset_id, 'delete', query, key)
    )


@asset_controller.post('/assets/{asset_id}/restore', summary='恢复素材身份及原目录归属')
@Log(title='恢复项目素材', business_type=BusinessType.UPDATE)
async def restore_asset(request: Request, asset_id: ProjectId, payload: AssetAction, key: Key, db: Db, user: User):
    return mutation_response(await AssetLifecycleService.mutate(db, user, asset_id, 'restore', payload, key))
