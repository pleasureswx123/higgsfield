"""文本分类段落、来源行号、重复别名及拒绝边界。"""
import unittest
from exceptions.exception import ServiceWarning
from module_higgsfield.service.element_text_parser_service import ElementTextParserService as Parser
from module_higgsfield.service.element_import_result_service import ElementImportResultService


class ElementTextParserTests(unittest.TestCase):
    def test_text_sections_preserve_source_and_description(self):
        rows = Parser.parse('\ufeff剧本标题\r\n角色：小明\r\n年轻记者\r\n\r\n场景：车站\r\n夜晚\r\n道具：笔记本'.encode(),
                            max_bytes=10000, project_name='样片', include_project_name=True)
        self.assertEqual([row.source_locator['line'] for row in rows], [2, 5, 7])
        self.assertEqual([row.candidate['category'] for row in rows], ['character', 'scene', 'prop'])
        self.assertEqual(rows[0].candidate['alias'], '样片_小明')
        self.assertEqual(rows[0].candidate['description'], '年轻记者')
        self.assertEqual(len(ElementImportResultService.validate(rows, 'txt')), 3)

    def test_markdown_code_is_literal_and_duplicates_remain_editable(self):
        rows = Parser.parse('# 剧本\n## 人物：小明\n说明\n```text\n道具：假的候选\n```\n## 角色：小明\n第二处'.encode(),
                            max_bytes=10000, markdown=True)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1].source_locator['line'], 7)
        self.assertIn('道具：假的候选', rows[0].candidate['description'])
        self.assertTrue(all(row.issues[0]['code'] == 'ELEMENT_ALIAS_DUPLICATE' for row in rows))
        self.assertEqual(len(ElementImportResultService.validate(rows, 'md')), 2)

    def test_invalid_text_never_silently_succeeds_or_truncates(self):
        for body in [b'\xff', b'plain prose', '角色：甲\n\x00'.encode(), '角色：甲\n```\n未闭合'.encode(),
                     ('角色：甲\n' + 'a' * 20001).encode()]:
            with self.subTest(body=body[:30]), self.assertRaises(ServiceWarning):
                Parser.parse(body, max_bytes=100000, markdown=True)
        with self.assertRaises(ServiceWarning):
            Parser.parse('角色：甲\n道具：乙'.encode(), max_bytes=10000, max_rows=1)
        with self.assertRaises(ServiceWarning):
            Parser.parse('角色：甲'.encode(), max_bytes=2)
        rows = Parser.parse('角色：\n待填写名称'.encode(), max_bytes=10000)
        self.assertEqual({item['field'] for item in rows[0].issues}, {'name', 'alias'})
