"""剧本格式识别与旧解析版本重放，所有候选仍需人工复核。"""
import unittest
from exceptions.exception import ServiceWarning
from module_higgsfield.service.element_import_formats import parse_document, parser_version, supports_version
from module_higgsfield.service.element_import_result_service import ElementImportResultService
from tests.test_higgsfield_element_docx_parser import docx
from tests.test_higgsfield_element_pdf_parser import pdf_pages


class ElementScreenplayParserTests(unittest.TestCase):
    def test_chinese_scene_dialogue_and_repeated_speakers_keep_evidence(self):
        body = '剧本标题\n第1场 内景：车站 夜\n旅客走过。\n记者（低声）：车来了吗？\n站长：还没有。\n记者：我再等等。'.encode()
        rows = parse_document(body, 'txt', max_bytes=10000)
        self.assertEqual([row.candidate['name'] for row in rows], ['车站 夜', '记者', '站长', '记者'])
        self.assertEqual([row.source_locator['line'] for row in rows], [2, 4, 5, 6])
        self.assertEqual(rows[0].candidate['category'], 'scene')
        self.assertIn('记者（低声）：车来了吗？', rows[1].candidate['description'])
        self.assertTrue(rows[1].issues)
        self.assertTrue(rows[3].issues)
        self.assertEqual(len(ElementImportResultService.validate(rows, 'txt')), 4)

    def test_english_cues_and_markdown_fences(self):
        body = 'INT. STATION - NIGHT\nA train arrives.\n\nREPORTER\nIs it here?\n\n```text\nEXT. FAKE\n```\nEXT. STREET - DAY\n备注：不作为人物'.encode()
        rows = parse_document(body, 'md', max_bytes=10000)
        self.assertEqual([row.candidate['name'] for row in rows], ['STATION - NIGHT', 'REPORTER', 'STREET - DAY'])
        self.assertIn('EXT. FAKE', rows[1].candidate['description'])
        with self.assertRaises(ServiceWarning):
            parse_document('这只是说明：正文\n并非带场景标记的剧本'.encode(), 'txt', max_bytes=10000)
        with self.assertRaises(ServiceWarning):
            parse_document('内景：车站\n记者：文字\x0b'.encode(), 'txt', max_bytes=10000)

    def test_legacy_versions_do_not_pick_up_new_rules(self):
        body = '角色：甲\n内景：车站\n甲：你好'.encode()
        legacy = parse_document(body, 'txt', version='element-text-v1', max_bytes=10000)
        current = parse_document(body, 'txt', max_bytes=10000)
        self.assertEqual(len(legacy), 1)
        self.assertEqual(len(current), 3)
        self.assertIn('内景：车站', legacy[0].candidate['description'])
        self.assertEqual(parser_version('txt'), 'element-screenplay-v2')
        self.assertFalse(supports_version('csv', 'element-screenplay-v2'))
        with self.assertRaises(ServiceWarning):
            parse_document(body, 'txt', version='element-pdf-v1', max_bytes=10000)

    def test_docx_and_pdf_map_screenplay_positions(self):
        body = docx('<w:p><w:r><w:t>内景：车站</w:t></w:r></w:p>'
                    '<w:p><w:r><w:t>记者：你好</w:t></w:r></w:p>')
        rows = parse_document(body, 'docx', max_bytes=100000)
        self.assertEqual(rows[1].source_locator, {'paragraph': 2, 'line': 1})
        body = pdf_pages(['内景：车站', '记者：你好'])
        rows = parse_document(body, 'pdf', max_bytes=100000)
        self.assertEqual(rows[1].source_locator, {'page': 2, 'line': 1})
