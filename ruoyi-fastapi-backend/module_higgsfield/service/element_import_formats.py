"""已实现的导入格式与固定解析版本，供受理、工作器和结果登记共用。"""
from module_higgsfield.service.element_import_parser_service import ElementImportParserService as TableParser
from module_higgsfield.service.element_text_parser_service import ElementTextParserService as TextParser
from module_higgsfield.service.element_docx_parser_service import ElementDocxParserService as DocxParser
from module_higgsfield.service.docx_content_service import DocxContentService
from module_higgsfield.service.element_pdf_parser_service import ElementPdfParserService as PdfParser
from module_higgsfield.service.element_screenplay_parser_service import ElementScreenplayParserService as ScriptParser

MIME_TYPES = {'csv': 'text/csv', 'xlsx': TableParser.xlsx_mime,
              'txt': 'text/plain', 'md': 'text/markdown', 'docx': DocxContentService.mime, 'pdf': 'application/pdf'}


def parser_version(source_format):
    if source_format in {'csv', 'xlsx'}:
        return TableParser.version
    if source_format in {'txt', 'md', 'docx', 'pdf'}:
        return ScriptParser.version
    return None


def supports_version(source_format, version):
    legacy = {'csv': TableParser.version, 'xlsx': TableParser.version, 'txt': TextParser.version,
              'md': TextParser.version, 'docx': DocxParser.version, 'pdf': PdfParser.version}
    return source_format in legacy and version in {legacy[source_format], parser_version(source_format)}


def parse_document(body, source_format, *, version=None, **options):
    version = version or parser_version(source_format)
    if not supports_version(source_format, version):
        TableParser.fail(0, '文件格式与固定解析版本不匹配')
    screenplay = version == ScriptParser.version
    if source_format == 'pdf':
        return PdfParser.parse(body, screenplay=screenplay, **options)
    if source_format == 'docx':
        return DocxParser.parse(body, screenplay=screenplay, **options)
    if source_format in {'txt', 'md'}:
        parser = ScriptParser if screenplay else TextParser
        return parser.parse(body, markdown=source_format == 'md', **options)
    if source_format == 'csv':
        return TableParser.csv(body, **options)
    if source_format == 'xlsx':
        return TableParser.xlsx(body, **options)
    TableParser.fail(0, '此文件格式尚未支持')
