"""图片比例和分辨率映射；版本一固定长边，短边四舍五入到16的倍数。"""

RATIOS = ('1:1', '3:2', '2:3', '16:9', '9:16', '4:3', '3:4', '21:9')
EDGES = {'1K': 1024, '2K': 2048, '4K': 3840}


class ImageSizeService:
    @staticmethod
    def size(ratio: str, resolution: str) -> str:
        if resolution not in EDGES:
            raise ValueError('不支持的图片分辨率')
        if ratio == 'Auto':
            return 'auto'
        if ratio not in RATIOS:
            raise ValueError('不支持的图片比例')
        width, height = map(int, ratio.split(':'))
        edge = EDGES[resolution]
        short = ((edge * min(width, height) + 8 * max(width, height)) // (16 * max(width, height))) * 16
        return f'{edge}x{short}' if width >= height else f'{short}x{edge}'

    @classmethod
    def parameters(cls, values: dict) -> dict:
        result = dict(values)
        if 'aspect_ratio' in result or 'resolution' in result:
            size = cls.size(result.pop('aspect_ratio', 'Auto'), result.pop('resolution', '2K'))
            if 'size' in result and result['size'] != size:
                raise ValueError('图片尺寸与比例分辨率映射不一致')
            result['size'] = size
        return result
