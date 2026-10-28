from typing import Annotated
from fastapi import Query, Request, Response
from common.aspect.pre_auth import PreAuthDependency
from common.annotation.log_annotation import Log
from common.enums import BusinessType
from common.router import APIRouterPro
from module_higgsfield.controller.project_workspace_controller import Db, User, Key, ProjectId, mutation_response
from module_higgsfield.entity.vo.price_vo import PriceBookCreate, PriceBookQuery
from module_higgsfield.service.price_service import PriceService
from utils.response_util import ResponseUtil
from module_higgsfield.entity.vo.price_vo import PriceSourceCreate
from module_higgsfield.service.price_source_service import PriceSourceService
from module_higgsfield.entity.vo.price_version_vo import PriceVersionCreate, PriceVersionPatch, PriceVersionQuery
from module_higgsfield.service.price_version_service import PriceVersionService
from module_higgsfield.entity.vo.price_version_vo import PriceSimulation
from module_higgsfield.entity.vo.price_publish_vo import PricePublish, PriceActivationEnd, PriceHistoryQuery
from module_higgsfield.service.price_publish_service import PricePublishService
from module_higgsfield.entity.vo.exchange_rate_vo import ExchangeRateCreate, ExchangeRatePublish, ExchangeRateQuery
from module_higgsfield.service.exchange_rate_service import ExchangeRateService


price_controller = APIRouterPro(
    prefix='/api/admin/v1', tags=['后台管理-价格'], order_num=91, dependencies=[PreAuthDependency()]
)


@price_controller.get('/exchange-rate-versions', summary='分页读取汇率版本')
async def exchange_rates(request: Request, query: Annotated[ExchangeRateQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await ExchangeRateService.listing(db, user, query))


@price_controller.post('/exchange-rate-versions', summary='登记有来源的汇率草稿')
@Log(title='登记汇率版本', business_type=BusinessType.INSERT)
async def create_exchange_rate(request: Request, payload: ExchangeRateCreate, key: Key, db: Db, user: User):
    return mutation_response(await ExchangeRateService.save(db, user, payload, key))


@price_controller.post('/exchange-rate-versions/{rate_id}/publish', summary='校验币对区间后发布汇率')
@Log(title='发布汇率版本', business_type=BusinessType.UPDATE)
async def publish_exchange_rate(
    request: Request, rate_id: ProjectId, payload: ExchangeRatePublish, key: Key, db: Db, user: User
):
    return mutation_response(await ExchangeRateService.save(db, user, payload, key, rate_id))


@price_controller.get('/price-books', summary='分页读取价格簿')
async def listing(request: Request, query: Annotated[PriceBookQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await PriceService.listing(db, user, query))


@price_controller.post('/price-books', summary='登记明确用途的价格簿')
@Log(title='登记价格簿', business_type=BusinessType.INSERT)
async def create(request: Request, payload: PriceBookCreate, key: Key, db: Db, user: User):
    return mutation_response(await PriceService.create(db, user, payload, key))


@price_controller.post('/price-sources', summary='登记不可变价格来源')
@Log(title='登记价格来源', business_type=BusinessType.INSERT)
async def create_source(request: Request, payload: PriceSourceCreate, key: Key, db: Db, user: User):
    return mutation_response(await PriceSourceService.create(db, user, payload, key))


@price_controller.get('/price-sources/{source_id}', summary='读取价格来源证据')
async def get_source(request: Request, source_id: ProjectId, db: Db, user: User):
    return ResponseUtil.success(data=await PriceSourceService.get(db, user, source_id))


@price_controller.get('/price-sources/{source_id}/attachment/download', summary='授权下载价格证据附件')
@price_controller.head('/price-sources/{source_id}/attachment/download', summary='授权读取价格证据附件元数据')
@price_controller.get('/price-sources/{source_id}/attachment', summary='读取价格证据附件（契约入口）')
@price_controller.head('/price-sources/{source_id}/attachment', summary='读取价格证据附件元数据（契约入口）')
async def source_attachment(request: Request, source_id: ProjectId, db: Db, user: User):
    stream, headers, mime, status = await PriceSourceService.download(
        db, user, source_id, request.headers.get('range'), head=request.method == 'HEAD')
    if request.method == 'HEAD':
        return Response(headers=headers, media_type=mime, status_code=status)
    return ResponseUtil.streaming(data=stream, headers=headers, media_type=mime, status_code=status)


@price_controller.get('/price-versions', summary='分页读取价格版本与校验问题')
async def versions(request: Request, query: Annotated[PriceVersionQuery, Query()], db: Db, user: User):
    return ResponseUtil.success(model_content=await PriceVersionService.listing(db, user, query))


@price_controller.get('/price-versions/{version_id}', summary='读取价格版本及来源')
async def version(request: Request, version_id: ProjectId, db: Db, user: User):
    return ResponseUtil.success(data=await PriceVersionService.get(db, user, version_id))


@price_controller.post('/price-versions', summary='新增价格草稿版本')
@Log(title='新增价格版本', business_type=BusinessType.INSERT)
async def create_version(request: Request, payload: PriceVersionCreate, key: Key, db: Db, user: User):
    return mutation_response(await PriceVersionService.save(db, user, payload, key))


@price_controller.patch('/price-versions/{version_id}', summary='编辑价格草稿并校验并发版本')
@Log(title='编辑价格版本', business_type=BusinessType.UPDATE)
async def patch_version(
    request: Request, version_id: ProjectId, payload: PriceVersionPatch, key: Key, db: Db, user: User
):
    return mutation_response(await PriceVersionService.save(db, user, payload, key, version_id))


@price_controller.post('/price-versions/{version_id}/simulate', summary='按精确规格离线试算价格，不写账本')
async def simulate_version(request: Request, version_id: ProjectId, payload: PriceSimulation, db: Db, user: User):
    return ResponseUtil.success(data=await PriceVersionService.simulate(db, user, version_id, payload))


@price_controller.post('/price-versions/{version_id}/publish', summary='原子发布价格及生效区间')
@Log(title='发布价格', business_type=BusinessType.UPDATE)
async def publish_version(request: Request, version_id: ProjectId, payload: PricePublish, key: Key, db: Db, user: User):
    return mutation_response(await PricePublishService.publish(db, user, version_id, payload, key))


@price_controller.post('/price-activations/{activation_id}/end', summary='结束价格生效区间并保留历史')
@Log(title='结束价格区间', business_type=BusinessType.UPDATE)
async def end_activation(
    request: Request, activation_id: ProjectId, payload: PriceActivationEnd, key: Key, db: Db, user: User
):
    return mutation_response(await PricePublishService.end(db, user, activation_id, payload, key))


@price_controller.get('/price-versions/{version_id}/history', summary='读取价格发布及生效区间历史')
async def price_history(
    request: Request, version_id: ProjectId, query: Annotated[PriceHistoryQuery, Query()], db: Db, user: User
):
    return ResponseUtil.success(model_content=await PricePublishService.history(db, user, version_id, query))
