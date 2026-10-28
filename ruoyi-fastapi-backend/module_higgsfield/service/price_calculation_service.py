"""纯计价内核：价格发布、权限和用量可信性由调用服务负责。"""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP, localcontext
import re


def decimal_value(value, precision, scale):
    """只接受普通十进制字符串，禁止浮点、指数及数据库隐式截断。"""
    if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9][0-9]*)(\.[0-9]+)?', value):
        raise ValueError('数量或金额必须为非负十进制字符串')
    whole, _, fraction = value.partition('.')
    if len(whole) > precision - scale or len(fraction) > scale:
        raise ValueError('数量或金额超出存储精度')
    return Decimal(value)


@dataclass(frozen=True)
class CalculationItem:
    id: int
    item_code: str
    unit: str
    unit_quantity: str
    unit_price: str
    quantity_from: str
    quantity_to: str | None
    formula_template: str
    free_reason: str | None = None


class PriceCalculationService:
    # 未定义缓存及字符计费模板前不开放对应项。
    sources = {
        'input': ('inputTokens', 'token'),
        'output': ('outputTokens', 'token'),
        'video_tokens': ('videoTokens', 'token'),
        'output_seconds': ('outputSeconds', 'second'),
        'reference_seconds': ('referenceSeconds', 'second'),
        'input_images': ('imageCount', 'image'),
    }

    @classmethod
    def calculate(cls, items, usage, *, calculation_scale, rounding_mode):
        """使用版本指定尺度汇总后量化，按余数及分项 ID 确定性分配。"""
        if type(calculation_scale) is not int or not 0 <= calculation_scale <= 10:
            raise ValueError('计算尺度必须在 0 到 10 之间')
        if rounding_mode != 'half_up' or not items or len(items) > 1000:
            raise ValueError('不支持的舍入方式或分项数量')
        allowed = {source for source, _ in cls.sources.values()}
        if set(usage) - allowed:
            raise ValueError('包含尚未支持的用量字段')
        quantities = {}
        for key, value in usage.items():
            if key == 'imageCount':
                if type(value) is not int or not 0 <= value <= 2147483647:
                    raise ValueError('图片数量必须为非负整数')
                value = str(value)
            if key.endswith('Tokens'):
                quantity = decimal_value(value, 19, 0)
                if quantity > 9223372036854775807:
                    raise ValueError('Token 数量超出 bigint 范围')
            else:
                quantity = decimal_value(value, 24, 6)
            quantities[key] = quantity
        with localcontext() as context:
            context.prec = 100
            groups = defaultdict(list)
            identities = set()
            for item in items:
                if type(item.id) is not int or not 0 < item.id <= 9223372036854775807 or item.id in identities:
                    raise ValueError('分项 ID 无效或重复')
                identities.add(item.id)
                if item.item_code not in cls.sources or item.unit != cls.sources[item.item_code][1]:
                    raise ValueError('分项或单位尚未支持')
                if item.formula_template not in ('linear', 'tiered'):
                    raise ValueError('公式模板尚未支持')
                base = decimal_value(item.unit_quantity, 18, 6)
                price = decimal_value(item.unit_price, 24, 10)
                start = decimal_value(item.quantity_from, 24, 6)
                end = None if item.quantity_to is None else decimal_value(item.quantity_to, 24, 6)
                if base <= 0 or (price == 0 and not (item.free_reason or '').strip()):
                    raise ValueError('基数必须大于零，零价必须说明原因')
                if end is not None and end <= start:
                    raise ValueError('阶梯上限必须大于下限')
                groups[item.item_code].append((start, end, item, base, price))
            lines = []
            quantum = Decimal(1).scaleb(-calculation_scale)
            for code, tiers in groups.items():
                tiers.sort(key=lambda row: row[0])
                source = cls.sources[code][0]
                if source not in quantities:
                    raise ValueError(f'缺少计费用量：{source}')
                cursor = Decimal(0)
                templates = {row[2].formula_template for row in tiers}
                if len(templates) != 1 or ('linear' in templates and len(tiers) != 1):
                    raise ValueError('同一分项不能混用公式或重复线性收费')
                for start, end, item, base, price in tiers:
                    if cursor is None or start != cursor:
                        raise ValueError('阶梯必须从零开始、连续且不重叠')
                    cursor = end
                    quantity = (
                        max(Decimal(0), min(quantities[source], end) - start)
                        if end is not None
                        else max(Decimal(0), quantities[source] - start)
                    )
                    if quantity >= Decimal('1000000000000000000'):
                        raise ValueError('分项数量超出存储精度')
                    raw = quantity / base * price
                    amount = raw.quantize(quantum, rounding=ROUND_DOWN)
                    lines.append(
                        {
                            'itemId': str(item.id),
                            'itemCode': code,
                            'quantity': str(quantity),
                            'unitQuantity': item.unit_quantity,
                            'unitPrice': item.unit_price,
                            '_raw': raw,
                            '_amount': amount,
                        }
                    )
                if cursor is not None:
                    raise ValueError('最后一个阶梯必须无上限')
            total = sum((line['_raw'] for line in lines), Decimal(0)).quantize(quantum, rounding=ROUND_HALF_UP)
            if total >= Decimal('100000000000000'):
                raise ValueError('计费总额超出存储精度')
            remaining = int((total - sum((line['_amount'] for line in lines), Decimal(0))) / quantum)
            ordered = sorted(lines, key=lambda line: (-(line['_raw'] - line['_amount']), int(line['itemId'])))
            for index, line in enumerate(ordered):
                allocation = quantum if index < remaining else Decimal(0)
                line['amount'] = format(line['_amount'] + allocation, 'f')
                line['rawAmount'] = format(line.pop('_raw'), 'f')
                line['truncatedAmount'] = format(line.pop('_amount'), 'f')
                line['allocatedAmount'] = format(allocation, 'f')
            return {
                'total': format(total, 'f'),
                'lines': sorted(lines, key=lambda line: int(line['itemId'])),
                'roundingMode': rounding_mode,
                'calculationScale': calculation_scale,
            }
