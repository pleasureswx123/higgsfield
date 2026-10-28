"""DOCX正文来源映射、包结构校验及候选诊断。"""
import io
import unittest
import zipfile
from exceptions.exception import ServiceWarning
from module_higgsfield.service.docx_content_service import DocxContentService as Content
from module_higgsfield.service.element_docx_parser_service import ElementDocxParserService as Parser
from module_higgsfield.service.element_import_result_service import ElementImportResultService


def docx(body, extra=None):
    parts = {
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            f'<Override PartName="/word/document.xml" ContentType="{Content.document_type}"/></Types>',
        '_rels/.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        'word/document.xml': f'<w:document xmlns:w="{Content.word}"><w:body>{body}</w:body></w:document>',
    }
    parts.update(extra or {})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, value in parts.items():
            archive.writestr(name, value.encode())
    return buffer.getvalue()


class ElementDocxParserTests(unittest.TestCase):
    def test_runs_tables_breaks_and_source_paragraphs(self):
        body = docx('<w:p><w:r><w:t>剧本</w:t></w:r></w:p>'
            '<w:p><w:r><w:t>角色：</w:t></w:r><w:r><w:t>记者</w:t><w:br/><w:t>年轻人</w:t></w:r></w:p>'
            '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>场景：车站</w:t><w:br/><w:t>夜晚</w:t>'
            '<w:br/><w:t>道具：手提箱</w:t></w:r></w:p></w:tc></w:tr></w:tbl>')
        rows = Parser.parse(body, max_bytes=100000)
        self.assertEqual([row.source_locator for row in rows], [
            {'paragraph': 2, 'line': 1}, {'paragraph': 3, 'line': 1}, {'paragraph': 3, 'line': 3}])
        self.assertEqual([row.candidate['description'] for row in rows], ['年轻人', '夜晚', ''])
        self.assertEqual(len(ElementImportResultService.validate(rows, 'docx')), 3)

    def test_deleted_and_drawing_text_not_imported_links_not_fetched(self):
        body = docx('<w:del><w:p><w:r><w:t>角色：已删除</w:t></w:r></w:p></w:del>'
            '<w:p><w:r><w:t>角色：甲</w:t></w:r><w:drawing><w:p><w:r><w:t>场景：图片</w:t>'
            '</w:r></w:p></w:drawing></w:p><w:p><w:hyperlink><w:r><w:t>外链显示文本</w:t>'
            '</w:r></w:hyperlink></w:p>')
        rows = Parser.parse(body, max_bytes=100000)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].candidate['description'], '外链显示文本')

    def test_rejects_invalid_packages_entities_macros_and_external_content(self):
        paragraph = '<w:p><w:r><w:t>角色：甲</w:t></w:r></w:p>'
        invalid = [b'not-a-docx', docx('<w:altChunk/>'), docx(paragraph, {'word/vbaProject.bin': 'macro'}),
            docx(paragraph, {'word/embeddings/object.bin': 'object'}),
            docx(paragraph, {'word/document.xml': '<!DOCTYPE doc [<!ENTITY x "bad">]><doc>&x;</doc>'}),
            docx(paragraph, {'_rels/.rels': '<Relationships/>'}),
            docx(paragraph, {'word/_rels/document.xml.rels': '<Relationships><Relationship TargetMode="External" Type="image" Target="https://example.invalid/x"/></Relationships>'})]
        for body in invalid:
            with self.subTest(size=len(body)), self.assertRaises(ServiceWarning):
                Parser.parse(body, max_bytes=100000)
        with self.assertRaises(ServiceWarning):
            Parser.parse(docx(paragraph), max_bytes=10)

    def test_duplicate_aliases_and_invalid_locator_are_not_hidden(self):
        paragraph = '<w:p><w:r><w:t>角色：甲</w:t></w:r></w:p>'
        rows = Parser.parse(docx(paragraph * 2), max_bytes=100000)
        self.assertTrue(all(row.issues[0]['code'] == 'ELEMENT_ALIAS_DUPLICATE' for row in rows))
        rows[1].source_locator['paragraph'] = 1
        with self.assertRaises(ServiceWarning):
            ElementImportResultService.validate(rows, 'docx')
