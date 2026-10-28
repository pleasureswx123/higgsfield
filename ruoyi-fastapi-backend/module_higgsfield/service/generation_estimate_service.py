"""已发布策略与固定价格的预估桥接，保留用量上界来源而不生成实际账单。"""

from module_higgsfield.entity.vo.model_capability_vo import ModelCapabilities
from module_higgsfield.service.price_calculation_service import CalculationItem, PriceCalculationService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService


class GenerationEstimateService:
    @staticmethod
    def calculate(
        capabilities: ModelCapabilities, *, model_version_id: str, input_snapshot: dict, prices: dict
    ) -> dict:
        policy = capabilities.estimate_policy
        if policy is None:
            WorkspaceService.conflict('GENERATION_ESTIMATE_UNAVAILABLE', '模型未发布可靠用量上界策略')
        usage = policy.upper_bounds.model_dump(by_alias=True, exclude_none=True)
        if set(prices) != {'platform', 'procurement'}:
            WorkspaceService.conflict('GENERATION_ESTIMATE_UNAVAILABLE', '预估必须具有完整的平台和采购价格快照')
        estimates = {}
        for purpose, price in prices.items():
            try:
                items = [
                    CalculationItem(
                        id=int(row['id']),
                        item_code=row['itemCode'],
                        unit=row['unit'],
                        unit_quantity=row['unitQuantity'],
                        unit_price=row['unitPrice'],
                        quantity_from=row['quantityFrom'],
                        quantity_to=row['quantityTo'],
                        formula_template=row['formulaTemplate'],
                        free_reason=row['freeReason'],
                    )
                    for row in price['items']
                ]
                # 只投影此价格实际计费字段；缺少任一字段由计价内核拒绝，不补零。
                required = {PriceCalculationService.sources[item.item_code][0] for item in items}
                calculated = PriceCalculationService.calculate(
                    items,
                    {name: value for name, value in usage.items() if name in required},
                    calculation_scale=price['calculationScale'],
                    rounding_mode=price['roundingMode'],
                )
            except (KeyError, ValueError, TypeError) as error:
                raise ValueError('预估策略与固定价格不完整或不兼容') from error
            estimates[purpose] = {
                'currency': price['currency'],
                'priceVersionId': price['priceVersionId'],
                **calculated,
            }
        return {
            'schemaVersion': 1,
            'modelVersionId': model_version_id,
            'inputHash': WriteService.digest(input_snapshot),
            'policy': policy.model_dump(by_alias=True),
            'usageUpperBounds': usage,
            'estimates': estimates,
        }
