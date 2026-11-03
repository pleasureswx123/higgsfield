"""测试发送前固定采购依据；缺规格或缺价明确保留未定价状态。"""
import re
from exceptions.exception import ServiceWarning
from module_higgsfield.dao.model_dao import ModelDao
from module_higgsfield.entity.vo.model_capability_vo import ModelCapabilities
from module_higgsfield.entity.vo.image_request_vo import ImageRequestParameters
from module_higgsfield.service.generation_input_service import GenerationInputService
from module_higgsfield.service.generation_price_service import GenerationPriceService
from module_higgsfield.dao.generation_price_dao import GenerationPriceDao
from module_higgsfield.dao.price_version_dao import PriceVersionDao
from module_higgsfield.service.price_version_service import PriceVersionService


class CredentialTestPriceService:
    @staticmethod
    async def freeze(db, binding, payload, *, currency, at):
        if currency is None:
            return {'state': 'unpriced', 'reason': 'CURRENCY_UNCONFIGURED'}
        if not isinstance(currency, str) or not re.fullmatch('[A-Z]{3}', currency):
            raise ValueError('采购币种必须由服务端策略明确指定')
        capabilities = ModelCapabilities.model_validate(binding.model_version.capabilities)
        parameters = {key: value for key, value in payload.items() if key not in {'model', 'messages'}}
        if binding.model_kind == 'image':
            parameters = ImageRequestParameters.model_validate(parameters).model_dump(exclude_none=True)
        elif 'has_video_input' in capabilities.variant_dimensions:
            parameters['has_video_input'] = False
        try:
            variant = GenerationInputService.select_variant(capabilities, parameters,
                await ModelDao.variants(db, binding.model_version.model_version_id))
            price = await GenerationPriceService.freeze_procurement(db, variant_id=variant.variant_id,
                account_id=binding.account.account_id, currency=currency, at=at)
        except ServiceWarning as exc:
            code = exc.data.get('errorCode') if isinstance(exc.data, dict) else None
            if code not in {'MODEL_VARIANT_UNAVAILABLE', 'PROCUREMENT_PRICE_UNAVAILABLE'}:
                raise
            if code == 'PROCUREMENT_PRICE_UNAVAILABLE' and binding.model_kind == 'video':
                # 首次模型测试发生在发布前，固定管理员刚确认的最新价格草稿。
                books = await GenerationPriceDao.procurement_books(db, variant.variant_id, binding.account.account_id, currency)
                if len(books) == 1:
                    drafts = await GenerationPriceDao.drafts(db, books[0].price_book_id)
                    if drafts:
                        version, book = drafts[0], books[0]
                        items, sources = await PriceVersionDao.children(db, [version.price_version_id])
                        if items and sources:
                            return {'state': 'fixed', 'price': {
                                'priceVersionId': str(version.price_version_id), 'priceBookId': str(book.price_book_id),
                                'modelVariantId': str(variant.variant_id), 'accountId': str(book.account_id),
                                'currency': currency, 'roundingMode': version.rounding_mode,
                                'calculationScale': version.calculation_scale,
                                'items': [PriceVersionService.item(item) for item in items], 'testDraft': True}}
            return {'state': 'unpriced', 'reason': code, 'currency': currency}
        return {'state': 'fixed', 'price': price}
