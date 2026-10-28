"""显式汇率版本发布及双向换算，不查询市场汇率或默认使用一比一。"""

from decimal import Decimal, ROUND_HALF_UP, localcontext
from common.vo import PageModel
from module_higgsfield.dao.exchange_rate_dao import ExchangeRateDao
from module_higgsfield.dao.price_source_dao import PriceSourceDao
from module_higgsfield.service.admin_scope_service import AdminScopeService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService
from module_higgsfield.service.price_calculation_service import decimal_value


class ExchangeRateService:
    @staticmethod
    def result(row):
        return {
            'id': str(row.exchange_rate_id),
            'baseCurrency': row.base_currency,
            'quoteCurrency': row.quote_currency,
            'rate': format(row.rate, 'f'),
            'validFrom': row.valid_from.isoformat(),
            'validUntil': row.valid_until.isoformat() if row.valid_until else None,
            'sourceId': str(row.source_id),
            'status': 'draft' if row.status == '0' else 'published',
            'revision': str(row.revision),
        }

    @classmethod
    async def listing(cls, db, user, query):
        await AdminScopeService.global_access(db, user, 'billing:price:read')
        rows, total = await ExchangeRateDao.page(db, query)
        return PageModel(
            rows=[cls.result(row) for row in rows],
            total=total,
            pageNum=query.page_num,
            pageSize=query.page_size,
            hasNext=query.page_num * query.page_size < total,
        )

    @classmethod
    async def save(cls, db, user, payload, key, identity=None):
        path = '/exchange-rate-versions' + (f'/{identity}/publish' if identity else '')
        prefix = '/api/admin/v1'
        data = payload.model_dump(by_alias=True, mode='json')
        try:
            await AdminScopeService.global_access(
                db, user, 'billing:price:publish' if identity else 'billing:price:write'
            )
            await WriteService.lock(db, user, path, key, api_prefix=prefix)
            replay = await WriteService.replay(db, user, path, key, data, api_prefix=prefix)
            if replay:
                await db.commit()
                return replay, True
            audit = WriteService.audit(user)
            before = None
            if identity:
                row = await ExchangeRateDao.get(db, identity)
                if row is None:
                    WorkspaceService.conflict('EXCHANGE_RATE_NOT_FOUND', '汇率版本不存在')
                await ExchangeRateDao.lock_pair(db, row.base_currency, row.quote_currency)
                row = await ExchangeRateDao.get(db, identity, lock=True)
                WorkspaceService.check_revision(row, payload.revision)
                if row.status != '0':
                    WorkspaceService.conflict('EXCHANGE_RATE_IMMUTABLE', '已发布汇率不可重新发布或修改')
                if await PriceSourceDao.get(db, row.source_id) is None:
                    WorkspaceService.conflict('PRICE_SOURCE_NOT_FOUND', '汇率来源不存在')
                if await ExchangeRateDao.overlap(db, row):
                    WorkspaceService.conflict('EXCHANGE_RATE_OVERLAP', '同一币对及反向币对的已发布区间不能重叠')
                before = cls.result(row)
                row.status = '1'
                row.revision += 1
                row.update_by, row.update_time = audit['update_by'], audit['update_time']
            else:
                if await PriceSourceDao.get(db, payload.source_id) is None:
                    WorkspaceService.conflict('PRICE_SOURCE_NOT_FOUND', '汇率来源不存在')
                row = await ExchangeRateDao.add(
                    db,
                    dict(
                        base_currency=payload.base_currency,
                        quote_currency=payload.quote_currency,
                        rate=Decimal(payload.rate),
                        valid_from=payload.valid_from,
                        valid_until=payload.valid_until,
                        source_id=int(payload.source_id),
                        **audit,
                    ),
                )
            after = cls.result(row)
            await PriceSourceDao.audit(
                db,
                dict(
                    actor_id=user.user.user_id,
                    actor_kind='user',
                    object_type='exchange_rate_version',
                    object_id=str(row.exchange_rate_id),
                    action='publish' if identity else 'create',
                    reason=payload.reason if identity else None,
                    request_id=WriteService.digest({'path': path, 'key': key}),
                    before_after={'before': before, 'after': after},
                    **audit,
                ),
            )
            return await WriteService.finish(
                db, user, path, key, data, after, 'exchange_rate_version', row.exchange_rate_id, api_prefix=prefix
            )
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    def convert(row, amount, source_currency, target_currency, *, at, scale):
        """调用方提供受理或对账所需的固定时点；返回可存入账本的换算快照。"""
        if type(scale) is not int or not 0 <= scale <= 10 or at.tzinfo is None:
            raise ValueError('换算必须指定有效尺度和带时区时点')
        if row.status != '1' or at < row.valid_from or (row.valid_until is not None and at >= row.valid_until):
            raise ValueError('指定汇率未发布或不适用于该时点')
        if source_currency == target_currency or {source_currency, target_currency} != {
            row.base_currency,
            row.quote_currency,
        }:
            raise ValueError('换算币种必须与汇率币对匹配；同币种无需换算')
        original = decimal_value(amount, 24, 10)
        rate = decimal_value(format(row.rate, 'f'), 24, 12)
        if rate <= 0:
            raise ValueError('汇率必须大于零')
        direction = 'multiply' if source_currency == row.base_currency else 'divide'
        with localcontext() as context:
            context.prec = 100
            raw = original * rate if direction == 'multiply' else original / rate
            result = raw.quantize(Decimal(1).scaleb(-scale), rounding=ROUND_HALF_UP)
            if result >= Decimal('100000000000000'):
                raise ValueError('换算金额超出存储精度')
        return {
            'exchangeRateVersionId': str(row.exchange_rate_id),
            'sourceCurrency': source_currency,
            'targetCurrency': target_currency,
            'sourceAmount': amount,
            'rate': format(rate, 'f'),
            'direction': direction,
            'rawAmount': format(raw, 'f'),
            'amount': format(result, 'f'),
            'roundingMode': 'half_up',
            'calculationScale': scale,
            'at': at.isoformat(),
        }
