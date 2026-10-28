"""PDF文本层分类候选，记录实际页号与提取文本行号。"""
from dataclasses import replace
from module_higgsfield.service.pdf_content_service import PdfContentService
from module_higgsfield.service.element_import_parser_service import ElementImportParserService as TableParser
from module_higgsfield.service.element_text_parser_service import ElementTextParserService


class ElementPdfParserService:
    version = 'element-pdf-v1'

    @classmethod
    def parse(cls, body, *, max_bytes, max_rows=10000, project_name='', include_project_name=False, screenplay=False):
        TableParser.limits(body, max_bytes, max_rows)
        try:
            pages = PdfContentService.pages(body, max_bytes=max_bytes)
        except Exception:
            TableParser.fail(0, 'PDF损坏、结构超限或无可提取文字')
        lines, locations = [], []
        for page, text in enumerate(pages, 1):
            for line, value in enumerate(text.splitlines() or [''], 1):
                lines.append(value)
                locations.append({'page': page, 'line': line})
        from module_higgsfield.service.element_screenplay_parser_service import ElementScreenplayParserService
        parser = ElementScreenplayParserService if screenplay else ElementTextParserService
        rows = parser.parse('\n'.join(lines).encode(), max_bytes=8 * 1024 * 1024,
            max_rows=max_rows, project_name=project_name, include_project_name=include_project_name)
        return [replace(row, source_locator=locations[row.source_locator['line'] - 1]) for row in rows]
