"""图片缩略图的受限文件处理；调用方在线程中执行，不持有数据库事务。"""
import hashlib
import io
import os
import uuid
import warnings

from PIL import Image, ImageOps

from exceptions.exception import ServiceWarning
from module_higgsfield.service.storage_service import StorageService


class ImageThumbnailService:
    """固定配方独立于原文件，后续配方变更必须使用新的版本标识。"""

    recipe = 'image-thumbnail-v1'
    max_edge = 512
    max_output_bytes = 2 * 1024 * 1024

    def __init__(self, storage=None):
        self.storage = storage or StorageService()

    @staticmethod
    def invalid():
        raise ServiceWarning(message='缩略图源文件无效或与归档事实不一致',
                             data={'errorCode': 'THUMBNAIL_SOURCE_INVALID'})

    def create(self, source_key, expected_sha256, expected_size, expected_mime):
        """仅接受内部归档定位与事实；生成文件尚未绑定时由调用方登记或清理。"""
        if expected_mime not in {'image/png', 'image/jpeg', 'image/webp'}:
            self.invalid()
        if type(expected_size) is not int or not 0 < expected_size <= self.storage.policy.max_bytes:
            self.invalid()
        key = 'media/' + uuid.uuid4().hex
        created = False
        try:
            with self.storage.open_key(source_key) as source:
                digest, size = hashlib.sha256(), 0
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    if size > expected_size:
                        self.invalid()
                    digest.update(chunk)
                if size != expected_size or digest.hexdigest() != expected_sha256:
                    self.invalid()
                source.seek(0)
                with warnings.catch_warnings():
                    warnings.simplefilter('error', Image.DecompressionBombWarning)
                    facts = self.storage.verify_media(source)
                    if facts['mime_type'] != expected_mime:
                        self.invalid()
                    source.seek(0)
                    with Image.open(source) as original:
                        # 像素校验已执行，EXIF仅用于方向，不写入缩略图。
                        oriented = ImageOps.exif_transpose(original)
                        try:
                            oriented.thumbnail((self.max_edge, self.max_edge), Image.Resampling.LANCZOS)
                            mode = 'RGBA' if 'A' in oriented.getbands() or 'transparency' in oriented.info else 'RGB'
                            converted = oriented.convert(mode)
                            try:
                                # 新像素对象不继承EXIF、ICC、注释或其他源元数据。
                                clean = Image.frombytes(mode, converted.size, converted.tobytes())
                                try:
                                    buffer = io.BytesIO()
                                    clean.save(buffer, format='WEBP', quality=82, method=4)
                                    encoded = buffer.getvalue()
                                    width, height = clean.size
                                finally:
                                    clean.close()
                            finally:
                                converted.close()
                        finally:
                            oriented.close()
            if not 0 < len(encoded) <= self.max_output_bytes:
                raise ServiceWarning(message='缩略图输出超出大小限制', data={'errorCode': 'THUMBNAIL_TOO_LARGE'})
            with self.storage.open_key(key, write=True) as output:
                created = True
                output.write(encoded)
                output.flush()
                os.fsync(output.fileno())
            return {'storage_key': key, 'sha256': hashlib.sha256(encoded).hexdigest(),
                    'byte_size': len(encoded), 'mime_type': 'image/webp',
                    'width': width, 'height': height, 'seconds': None}
        except Exception as cause:
            if created:
                self.storage.remove_unbound_key(key)
            if isinstance(cause, (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning)):
                self.invalid()
            raise
