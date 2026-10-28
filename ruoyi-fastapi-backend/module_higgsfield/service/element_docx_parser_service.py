"""DOCX正文分类段落生成候选，并映射到原始段落及段落内行号。"""
from dataclasses import replace
from module_higgsfield.service.docx_content_service import DocxContentService
from module_higgsfield.service.element_import_parser_service import ElementImportParserService as TableParser
from module_higgsfield.service.element_text_parser_service import ElementTextParserService


class ElementDocxParserService:
    version = 'element-docx-v1'

    @classmethod
    def parse(cls, body, *, max_bytes, max_rows=10000, project_name='', include_project_name=False, screenplay=False):
        TableParser.limits(body, max_bytes, max_rows)
        try:
            paragraphs = DocxContentService.paragraphs(body, max_bytes=max_bytes)
        except Exception:
            # 压缩/XML库异常不把文档正文带到用户响应。
            TableParser.fail(0, 'DOCX结构损坏或正文不受支持')
        lines, locations = [], []
        for paragraph, value in enumerate(paragraphs, 1):
            for line, text in enumerate(value.splitlines() or [''], 1):
                lines.append(text)
                locations.append({'paragraph': paragraph, 'line': line})
        content = '\n'.join(lines).encode('utf-8')
        from module_higgsfield.service.element_screenplay_parser_service import ElementScreenplayParserService
        parser = ElementScreenplayParserService if screenplay else ElementTextParserService
        rows = parser.parse(content, max_bytes=min(max_bytes * 10, 64 * 1024 * 1024),
            max_rows=max_rows, project_name=project_name, include_project_name=include_project_name)
        return [replace(row, source_locator=locations[row.source_locator['line'] - 1]) for row in rows]
