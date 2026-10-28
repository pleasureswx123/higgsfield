"""真实中文PDF文本层提取和候选页号映射。"""
import io
import unittest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject, ArrayObject
from exceptions.exception import ServiceWarning
from module_higgsfield.service.pdf_content_service import PdfContentService
from module_higgsfield.service.element_pdf_parser_service import ElementPdfParserService as Parser
from module_higgsfield.service.element_import_result_service import ElementImportResultService


def pdf_pages(pages, encrypted=False):
    writer = PdfWriter()
    chars = sorted(set(''.join(pages)) - {'\n'})
    mapping = '\n'.join(f'<{ord(c):04x}> <{ord(c):04x}>' for c in chars)
    cmap = DecodedStreamObject()
    cmap.set_data(('begincmap\n1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n'
                   f'{len(chars)} beginbfchar\n{mapping}\nendbfchar\nendcmap').encode())
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type0'),
        NameObject('/BaseFont'): NameObject('/STSong-Light'), NameObject('/Encoding'): NameObject('/Identity-H'),
        NameObject('/ToUnicode'): writer._add_object(cmap), NameObject('/DescendantFonts'): ArrayObject()})
    for text in pages:
        page = writer.add_blank_page(width=600, height=800)
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        stream = DecodedStreamObject()
        lines = ['BT /F1 12 Tf 14 TL 50 750 Td']
        for line in text.split('\n'):
            lines.append(f'<{line.encode("utf-16-be").hex()}> Tj T*')
        lines.append('ET')
        stream.set_data('\n'.join(lines).encode())
        page[NameObject('/Contents')] = writer._add_object(stream)
    if encrypted:
        writer.encrypt('test-password')
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class ElementPdfParserTests(unittest.TestCase):
    def test_chinese_text_and_page_positions(self):
        body = pdf_pages(['角色：记者\n年轻人', '场景：车站\n夜晚\n道具：手提箱'])
        rows = Parser.parse(body, max_bytes=100000)
        self.assertEqual([row.candidate['name'] for row in rows], ['记者', '车站', '手提箱'])
        self.assertEqual([row.source_locator for row in rows], [{'page': 1, 'line': 1}, {'page': 2, 'line': 1}, {'page': 2, 'line': 3}])
        self.assertEqual(rows[0].candidate['description'], '年轻人')
        self.assertEqual(len(ElementImportResultService.validate(rows, 'pdf')), 3)

    def test_blank_encrypted_wrong_signature_and_limits_rejected(self):
        for body in [b'fake', pdf_pages(['']), pdf_pages(['角色：甲'], encrypted=True)]:
            with self.subTest(size=len(body)), self.assertRaises(ServiceWarning):
                Parser.parse(body, max_bytes=100000)
        with self.assertRaises(ValueError):
            PdfContentService.pages(pdf_pages(['角色：甲']), max_bytes=10)
        with self.assertRaises(ServiceWarning):
            Parser.parse(pdf_pages(['角色：甲\n角色：乙']), max_bytes=100000, max_rows=1)
