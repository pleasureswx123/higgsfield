"""PDF解析门面；上传与候选解析均经过受限子进程。"""
from module_higgsfield.service.document_process_service import DocumentProcessService


class PdfContentService:
    mime = 'application/pdf'

    @staticmethod
    def pages(body, *, max_bytes):
        return DocumentProcessService.pdf_pages(body, max_bytes=max_bytes)
