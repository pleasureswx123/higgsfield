from fastapi import Request, Response
from common.aspect.pre_auth import PreAuthDependency
from common.router import APIRouterPro
from module_higgsfield.controller.project_workspace_controller import Db, User, ProjectId, Key, mutation_response
from module_higgsfield.entity.vo.asset_vo import OutputToAsset
from module_higgsfield.service.output_asset_service import OutputAssetService
from module_higgsfield.service.output_read_service import OutputReadService
from module_higgsfield.entity.vo.output_status_vo import OutputStatusUpdate
from module_higgsfield.service.output_status_service import OutputStatusService
from utils.response_util import ResponseUtil

output_controller = APIRouterPro(
    prefix='/api/v1', tags=['制作平台-生成输出'], order_num=88, dependencies=[PreAuthDependency()]
)


@output_controller.post('/outputs/{output_id}/to-asset', summary='将已归档作品转为独立素材并保留来源')
async def to_asset(request: Request, output_id: ProjectId, payload: OutputToAsset, key: Key, db: Db, user: User):
    return mutation_response(await OutputAssetService.create(db, user, output_id, payload, key))


@output_controller.get('/outputs/{output_id}', summary='读取已授权生成输出')
async def get(request: Request, output_id: ProjectId, db: Db, user: User):
    return ResponseUtil.success(data=await OutputReadService.get(db, user, output_id))


@output_controller.post('/outputs/{output_id}/work-status', summary='修改已归档作品工作状态并保留历史')
async def work_status(request: Request, output_id: ProjectId, payload: OutputStatusUpdate, key: Key, db: Db, user: User):
    return mutation_response(await OutputStatusService.update(db, user, output_id, payload, key))


@output_controller.get('/outputs/{output_id}/thumbnail', summary='授权读取作品图片缩略图')
@output_controller.head('/outputs/{output_id}/thumbnail', summary='授权读取作品缩略图元数据')
async def thumbnail(request: Request, output_id: ProjectId, db: Db, user: User):
    stream, headers, mime, status = await OutputReadService.media(
        db, user, output_id, request.headers.get('range'), head=request.method == 'HEAD', thumbnail=True
    )
    if request.method == 'HEAD':
        return Response(headers=headers, media_type=mime, status_code=status)
    return ResponseUtil.streaming(data=stream, headers=headers, media_type=mime, status_code=status)


@output_controller.get('/outputs/{output_id}/preview', summary='授权预览已归档输出')
@output_controller.head('/outputs/{output_id}/preview', summary='读取已归档输出预览元数据')
async def preview(request: Request, output_id: ProjectId, db: Db, user: User):
    stream, headers, mime, status = await OutputReadService.media(
        db, user, output_id, request.headers.get('range'), head=request.method == 'HEAD'
    )
    if request.method == 'HEAD':
        return Response(headers=headers, media_type=mime, status_code=status)
    return ResponseUtil.streaming(data=stream, headers=headers, media_type=mime, status_code=status)


@output_controller.get('/outputs/{output_id}/download', summary='授权下载已归档输出')
@output_controller.head('/outputs/{output_id}/download', summary='读取已归档输出下载元数据')
async def download(request: Request, output_id: ProjectId, db: Db, user: User):
    stream, headers, mime, status = await OutputReadService.media(
        db, user, output_id, request.headers.get('range'), download=True, head=request.method == 'HEAD'
    )
    if request.method == 'HEAD':
        return Response(headers=headers, media_type=mime, status_code=status)
    return ResponseUtil.streaming(data=stream, headers=headers, media_type=mime, status_code=status)
