"""参考图的平台保护限制；不代表供应商公布的容量承诺。"""

import os


def validate_image_references(media: list[dict]) -> None:
    single = int(os.environ.get('HF_IMAGE_REFERENCE_MAX_BYTES', str(10 * 1024 * 1024)))
    total_limit = int(os.environ.get('HF_IMAGE_REFERENCES_MAX_BYTES', str(32 * 1024 * 1024)))
    if not 0 < single <= total_limit <= 128 * 1024 * 1024:
        raise ValueError('参考图容量配置无效')
    total = 0
    for item in media:
        size = int(item['byteSize'])
        total += size
        if item['mimeType'] not in ('image/png', 'image/jpeg', 'image/webp'):
            raise ValueError('参考图仅支持PNG、JPEG、WebP')
        if not 0 < size <= single or total > total_limit:
            raise ValueError(f'参考图超过平台限制：单张 {single // 1048576} MiB、合计 {total_limit // 1048576} MiB，请减少图片或自行调整原图')
