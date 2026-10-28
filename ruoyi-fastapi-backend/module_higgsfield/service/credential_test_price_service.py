"""测试发送前固定采购依据；缺规格或缺价明确保留未定价状态。"""
import re
from exceptions.exception import ServiceWarning
from module_higgsfield.dao.model_dao import ModelDao
from module_higgsfield.entity.vo.model_capability_vo import ModelCapabilities
from module_higgsfield.entity.vo.image_request_vo import ImageRequestParameters
from module_higgsfield.service.generation_input_service import GenerationInputService
from module_higgsfield.service.generation_price_service import GenerationPriceService


class CredentialTestPriceService:
    @staticmethod
    async def freeze(db, binding, payload, *, currency, at):
        if currency is None:
            return {'state': 'unpriced', 'reason': 'CURRENCY_UNCONFIGURED'}
        if not isinstance(currency, str) or not re.fullmatch('[A-Z]{3}', currency):
            raise ValueError('采购币种必须由服务端策略明确指定')
        capabilities = ModelCapabilities.model_validate(binding.model_version.capabilities)
        parameters = ImageRequestParameters.model_validate({key: value for key, value in payload.items()
            if key not in {'model', 'messages'}}).model_dump(exclude_none=True)
        try:
            variant = GenerationInputService.select_variant(capabilities, parameters,
                await ModelDao.variants(db, binding.model_version.model_version_id))
            price = await GenerationPriceService.freeze_procurement(db, variant_id=variant.variant_id,
                account_id=binding.account.account_id, currency=currency, at=at)
        except ServiceWarning as exc:
            code = exc.data.get('errorCode') if isinstance(exc.data, dict) else None
            if code not in {'MODEL_VARIANT_UNAVAILABLE', 'PROCUREMENT_PRICE_UNAVAILABLE'}:
                raise
            return {'state': 'unpriced', 'reason': code, 'currency': currency}
        return {'state': 'fixed', 'price': price}
