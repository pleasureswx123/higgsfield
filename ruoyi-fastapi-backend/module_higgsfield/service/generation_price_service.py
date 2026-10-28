"""固定平台价和所选账号采购价；不默认币种，不将未定价解释为免费。"""

import re
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from module_higgsfield.dao.generation_price_dao import GenerationPriceDao
from module_higgsfield.dao.price_version_dao import PriceVersionDao
from module_higgsfield.service.price_version_service import PriceVersionService
from module_higgsfield.service.project_workspace_service import WorkspaceService


class GenerationPriceService:
    @classmethod
    async def freeze_procurement(cls, db, *, variant_id, account_id, currency, at):
        """管理测试等非项目消费只固定明确币种的账号采购价，不依赖平台价。"""
        if not isinstance(at, datetime) or at.tzinfo is None or at.utcoffset() is None:
            raise ValueError('定价时点必须含时区')
        if not isinstance(currency, str) or not re.fullmatch('[A-Z]{3}', currency):
            raise ValueError('采购币种必须由服务端策略明确指定')
        books = await GenerationPriceDao.procurement_books(db, variant_id, account_id, currency)
        if len(books) != 1:
            WorkspaceService.conflict('PROCUREMENT_PRICE_UNAVAILABLE', '无法唯一匹配规格、账号及币种的采购价格簿')
        book = books[0]
        active = await GenerationPriceDao.active(db, book.price_book_id, at)
        if len(active) != 1:
            WorkspaceService.conflict('PROCUREMENT_PRICE_UNAVAILABLE', '当前时点无法唯一匹配已发布采购价格')
        activation, version = active[0]
        items, sources = await PriceVersionDao.children(db, [version.price_version_id])
        if not items or not sources:
            WorkspaceService.conflict('PROCUREMENT_PRICE_UNAVAILABLE', '采购价格缺少分项或来源依据')
        return cls.snapshot(book, activation, version, items, sources, variant_id, at)

    @staticmethod
    def snapshot(book, activation, version, items, sources, variant_id, at):
        """两个计价入口共用固定证据投影，金额保持十进制字符串。"""
        return {
            'priceBookId': str(book.price_book_id), 'priceVersionId': str(version.price_version_id),
            'activationId': str(activation.activation_id), 'activationRevision': str(activation.revision),
            'currency': book.currency, 'accountId': str(book.account_id) if book.account_id else None,
            'modelVariantId': str(variant_id), 'selectedAt': at.isoformat(),
            'effectiveFrom': activation.effective_from.isoformat(),
            'effectiveUntil': activation.effective_until.isoformat() if activation.effective_until else None,
            'roundingMode': version.rounding_mode, 'calculationScale': version.calculation_scale,
            'items': [PriceVersionService.item(item) for item in items],
            'sourceIds': [str(source.source_id) for source in sources],
        }

    @classmethod
    async def freeze(
        cls, db: AsyncSession, *, variant_id: int, account_id: int, currencies: dict[str, str], at: datetime
    ) -> dict:
        """调用方先锁定路由和模型；币种来自服务端策略，返回值仅供内部任务快照。"""
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError('定价时点必须含时区')
        if set(currencies) != {'platform', 'procurement'} or any(
            not isinstance(value, str) or not re.fullmatch('[A-Z]{3}', value) for value in currencies.values()
        ):
            raise ValueError('必须显式指定平台与采购计价币种')
        books = await GenerationPriceDao.books(db, variant_id, account_id, currencies)
        if len(books) != len(currencies) or {book.purpose for book in books} != set(currencies):
            WorkspaceService.conflict('GENERATION_PRICE_UNAVAILABLE', '缺少对应规格、账号或币种的价格簿')
        result = {}
        for book in books:
            active = await GenerationPriceDao.active(db, book.price_book_id, at)
            if len(active) != 1:
                WorkspaceService.conflict('GENERATION_PRICE_UNAVAILABLE', '受理时点无法唯一匹配已发布价格')
            activation, version = active[0]
            items, sources = await PriceVersionDao.children(db, [version.price_version_id])
            if not items or not sources:
                WorkspaceService.conflict('GENERATION_PRICE_UNAVAILABLE', '已发布价格缺少分项或来源依据')
            result[book.purpose] = cls.snapshot(book, activation, version, items, sources, variant_id, at)
        return result
