"""价格版本聚合事务；版本号分配与草稿编辑在价格簿行锁下完成。"""

from common.vo import PageModel
from module_higgsfield.dao.price_version_dao import PriceVersionDao
from module_higgsfield.dao.price_source_dao import PriceSourceDao
from module_higgsfield.service.admin_scope_service import AdminScopeService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService
from module_higgsfield.service.price_calculation_service import PriceCalculationService, CalculationItem
from module_higgsfield.entity.vo.model_capability_vo import scalar_equal
from module_higgsfield.dao.exchange_rate_dao import ExchangeRateDao
from module_higgsfield.service.exchange_rate_service import ExchangeRateService
from utils.time_util import TimezoneUtil


class PriceVersionService:
    @classmethod
    async def simulate(cls, db, user, identity, payload):
        await AdminScopeService.global_access(db, user, 'billing:price:read')
        version = await PriceVersionDao.version(db, identity, lock=True)
        if version is None:
            WorkspaceService.conflict('PRICE_VERSION_NOT_FOUND', '价格版本不存在')
        scope = await PriceVersionDao.simulation_scope(db, version.price_book_id)
        if scope is None:
            WorkspaceService.conflict('PRICE_VARIANT_NOT_FOUND', '价格簿或关联模型规格不存在')
        book, variant = scope
        if set(payload.dimensions) != set(variant.dimensions) or any(
            not scalar_equal(payload.dimensions[name], value) for name, value in variant.dimensions.items()
        ):
            WorkspaceService.conflict('PRICE_VARIANT_MISMATCH', '试算必须提供与价格簿完全一致的模型规格维度')
        items, sources = await PriceVersionDao.children(db, [version.price_version_id])
        try:
            calculated = PriceCalculationService.calculate(
                cls.calculation_items(items),
                payload.usage.model_dump(by_alias=True, exclude_none=True),
                calculation_scale=version.calculation_scale,
                rounding_mode=version.rounding_mode,
            )
        except ValueError as error:
            WorkspaceService.conflict('PRICE_SIMULATION_INVALID', str(error))
        warnings = []
        if version.status == '0':
            warnings.append('当前为草稿价格，试算不代表已发布或已生效')
        if not sources:
            warnings.append('尚未绑定价格来源证据')
        result = {
            'matchedVariantId': str(variant.variant_id),
            'priceVersionId': str(version.price_version_id),
            'currency': book.currency,
            'lines': [
                {name: line[name] for name in ('itemCode', 'quantity', 'unitQuantity', 'unitPrice', 'amount')}
                for line in calculated['lines']
            ],
            'total': calculated['total'],
            'roundingMode': version.rounding_mode,
            'warnings': warnings,
        }
        if payload.exchange_rate_version_id is not None:
            rate = await ExchangeRateDao.get(db, payload.exchange_rate_version_id)
            if rate is None:
                WorkspaceService.conflict('EXCHANGE_RATE_NOT_FOUND', '指定汇率版本不存在')
            target = rate.quote_currency if book.currency == rate.base_currency else rate.base_currency
            try:
                result['conversion'] = ExchangeRateService.convert(
                    rate,
                    calculated['total'],
                    book.currency,
                    target,
                    at=TimezoneUtil.utc_now(),
                    scale=version.calculation_scale,
                )
            except ValueError as error:
                WorkspaceService.conflict('EXCHANGE_RATE_INVALID', str(error))
        return result

    @staticmethod
    def item(row):
        return {
            'id': str(row.item_id),
            'itemCode': row.item_code,
            'unit': row.unit,
            'unitQuantity': format(row.unit_quantity, 'f'),
            'unitPrice': format(row.unit_price, 'f'),
            'quantityFrom': format(row.quantity_from, 'f'),
            'quantityTo': format(row.quantity_to, 'f') if row.quantity_to is not None else None,
            'formulaTemplate': row.formula_template,
            'freeReason': row.free_reason,
        }

    @staticmethod
    def calculation_items(items):
        return [
            CalculationItem(
                row.item_id,
                row.item_code,
                row.unit,
                format(row.unit_quantity, 'f'),
                format(row.unit_price, 'f'),
                format(row.quantity_from, 'f'),
                format(row.quantity_to, 'f') if row.quantity_to is not None else None,
                row.formula_template,
                row.free_reason,
            )
            for row in items
        ]

    @classmethod
    def result(cls, version, items, sources):
        issues = []
        if not sources:
            issues.append(
                {'path': '/sourceIds', 'code': 'PRICE_SOURCE_REQUIRED', 'message': '发布前至少绑定一份来源证据'}
            )
        rules = cls.calculation_items(items)
        usage = {name: 0 if name == 'imageCount' else '0' for name, _ in PriceCalculationService.sources.values()}
        try:
            PriceCalculationService.calculate(
                rules, usage, calculation_scale=version.calculation_scale, rounding_mode=version.rounding_mode
            )
        except ValueError as error:
            issues.append({'path': '/items', 'code': 'PRICE_ITEMS_INCOMPLETE', 'message': str(error)})
        return {
            'id': str(version.price_version_id),
            'priceBookId': str(version.price_book_id),
            'versionNo': version.version_no,
            'status': 'draft' if version.status == '0' else 'published',
            'revision': str(version.revision),
            'roundingMode': version.rounding_mode,
            'calculationScale': version.calculation_scale,
            'items': [cls.item(row) for row in items],
            'sourceIds': [str(row.source_id) for row in sources],
            'validationIssues': issues,
        }

    @classmethod
    async def result_for(cls, db, version):
        items, sources = await PriceVersionDao.children(db, [version.price_version_id])
        return cls.result(version, items, sources)

    @classmethod
    async def get(cls, db, user, identity):
        await AdminScopeService.global_access(db, user, 'billing:price:read')
        version = await PriceVersionDao.version(db, identity, lock=True)
        if version is None:
            WorkspaceService.conflict('PRICE_VERSION_NOT_FOUND', '价格版本不存在')
        return await cls.result_for(db, version)

    @classmethod
    async def listing(cls, db, user, query):
        await AdminScopeService.global_access(db, user, 'billing:price:read')
        rows, total = await PriceVersionDao.page(db, query)
        items, sources = await PriceVersionDao.children(db, [row.price_version_id for row in rows])
        return PageModel(
            rows=[
                cls.result(
                    row,
                    [item for item in items if item.price_version_id == row.price_version_id],
                    [source for source in sources if source.price_version_id == row.price_version_id],
                )
                for row in rows
            ],
            total=total,
            pageNum=query.page_num,
            pageSize=query.page_size,
            hasNext=query.page_num * query.page_size < total,
        )

    @classmethod
    async def save(cls, db, user, payload, key, identity=None):
        path = '/price-versions' + (f'/{identity}' if identity else '')
        prefix, method = '/api/admin/v1', 'PATCH' if identity else 'POST'
        data = payload.model_dump(by_alias=True, exclude_unset=True)
        try:
            await AdminScopeService.global_access(db, user, 'billing:price:write')
            await WriteService.lock(db, user, path, key, api_prefix=prefix)
            replay = await WriteService.replay(db, user, path, key, data, method, api_prefix=prefix)
            if replay:
                await db.commit()
                return replay, True
            before = None
            if identity:
                version = await PriceVersionDao.version(db, identity)
                if version is None:
                    WorkspaceService.conflict('PRICE_VERSION_NOT_FOUND', '价格版本不存在')
                book_id = version.price_book_id
            else:
                book_id = int(payload.price_book_id)
            book = await PriceVersionDao.book(db, book_id)
            if book is None:
                WorkspaceService.conflict('PRICE_BOOK_NOT_FOUND', '价格簿不存在')
            audit = WriteService.audit(user)
            if identity:
                version = await PriceVersionDao.version(db, identity, lock=True)
                if version.status != '0':
                    WorkspaceService.conflict('PRICE_VERSION_IMMUTABLE', '已发布价格正文不可修改')
                WorkspaceService.check_revision(version, payload.revision)
                before = await cls.result_for(db, version)
                for name in ('calculation_scale', 'rounding_mode'):
                    if name in payload.model_fields_set:
                        setattr(version, name, getattr(payload, name))
                version.revision += 1
                version.update_by, version.update_time = audit['update_by'], audit['update_time']
            else:
                version = await PriceVersionDao.add(
                    db, book_id, user.user.user_id, payload.calculation_scale, payload.rounding_mode, audit
                )
            if payload.source_ids is not None and not await PriceVersionDao.sources_exist(db, payload.source_ids):
                WorkspaceService.conflict('PRICE_SOURCE_NOT_FOUND', '绑定的价格来源不存在')
            await PriceVersionDao.replace(db, version.price_version_id, payload.items, payload.source_ids, audit)
            after = await cls.result_for(db, version)
            await PriceSourceDao.audit(
                db,
                dict(
                    actor_id=user.user.user_id,
                    actor_kind='user',
                    object_type='price_version',
                    object_id=str(version.price_version_id),
                    action='update' if identity else 'create',
                    request_id=WriteService.digest({'path': path, 'key': key}),
                    before_after={'before': before, 'after': after},
                    **audit,
                ),
            )
            return await WriteService.finish(
                db, user, path, key, data, after, 'price_version', version.price_version_id, method, api_prefix=prefix
            )
        except Exception:
            await db.rollback()
            raise
