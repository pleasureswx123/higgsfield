"""PDF文本层提取，保留实际页序号；不执行动作，不进行OCR。"""
import io
from pypdf import PdfReader


class PdfContentService:
    mime = 'application/pdf'

    @staticmethod
    def pages(body, *, max_bytes):
        if not body or len(body) > max_bytes or not body.startswith(b'%PDF-'):
            raise ValueError('PDF文件大小或签名无效')
        reader = PdfReader(io.BytesIO(body), strict=True)
        if reader.is_encrypted:
            raise ValueError('不支持加密PDF')
        root = reader.root_object
        names = root.get('/Names', {})
        if hasattr(names, 'get_object'):
            names = names.get_object()
        if any(key in root for key in ('/OpenAction', '/AA')) or any(key in names for key in ('/JavaScript', '/EmbeddedFiles')):
            raise ValueError('不支持主动内容或附件')
        if not 1 <= len(reader.pages) <= 200:
            raise ValueError('PDF页数超过限制')
        result, decoded_size, text_size = [], 0, 0
        for page in reader.pages:
            if '/AA' in page:
                raise ValueError('不支持页面动作')
            content = page.get_contents()
            size = len(content.get_data()) if content is not None else 0
            decoded_size += size
            if size > 8 * 1024 * 1024 or decoded_size > 32 * 1024 * 1024:
                raise ValueError('PDF内容流超过限制')
            text = page.extract_text() or ''
            text_size += len(text)
            if text_size > 2000000:
                raise ValueError('PDF提取文字超过限制')
            result.append(text)
        if not any(text.strip() for text in result):
            raise ValueError('PDF无可提取文本，需要OCR')
        return result
