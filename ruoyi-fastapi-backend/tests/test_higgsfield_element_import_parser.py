"""元素表格候选的来源定位、可修正错误与安全边界。"""
import io
import unittest
from openpyxl import Workbook
from exceptions.exception import ServiceWarning
from module_higgsfield.service.element_import_parser_service import ElementImportParserService as Parser


class ElementImportParserTests(unittest.TestCase):
    def workbook(self, rows, *, extra_sheet=False):
        book = Workbook()
        book.active.title = '元素'
        for row in rows:
            book.active.append(row)
        if extra_sheet:
            book.create_sheet('第二张')
        buffer = io.BytesIO()
        book.save(buffer)
        book.close()
        return buffer.getvalue()

    def test_csv_keeps_line_locations_and_editable_invalid_candidates(self):
        body = '\ufeff名称,别名,分类,描述\n\n角色甲,001,角色,"第一行\n第二行"\n角色乙,001,未知分类,说明\n, ,道具,缺少名称\n'.encode()
        rows = Parser.csv(body, max_bytes=10000, project_name='测试项目', include_project_name=True)
        self.assertEqual([row.row_no for row in rows], [1, 2, 3])
        self.assertEqual([row.source_locator['line'] for row in rows], [3, 5, 6])
        self.assertEqual(rows[0].candidate['alias'], '测试项目_001')
        self.assertEqual(rows[0].candidate['category'], 'character')
        self.assertEqual(rows[0].candidate['description'], '第一行\n第二行')
        self.assertEqual(rows[1].candidate['category'], '未知分类')
        self.assertIn('ELEMENT_ALIAS_DUPLICATE', [item['code'] for item in rows[0].issues])
        self.assertIn('category', [item['field'] for item in rows[1].issues])
        self.assertEqual({item['field'] for item in rows[2].issues}, {'name', 'alias'})

    def test_csv_structural_errors_and_capacity_are_not_silently_truncated(self):
        for body in (b'name,alias,category,description\na,a,prop', b'wrong,header\nx,y',
                     b'name,alias,category,description\na,a,prop,"unfinished', b'\xff',
                     b'name,alias,category,description\n', b'name,alias,category,description\na,a,prop,\x00'):
            with self.subTest(body=body), self.assertRaises(ServiceWarning):
                Parser.csv(body, max_bytes=10000)
        body = b'name,alias,category,description\na,001,prop,one\nb,002,prop,two'
        with self.assertRaises(ServiceWarning):
            Parser.csv(body, max_bytes=10000, max_rows=1)
        with self.assertRaises(ServiceWarning):
            Parser.csv(body, max_bytes=2)
        with self.assertRaises(ValueError):
            Parser.csv(body, max_bytes=10000, include_project_name=True)

    def test_xlsx_text_identity_blank_rows_and_empty_description(self):
        body = self.workbook([Parser.columns, [], ['主角', '0001', 'character', None],
                              ['道具', '9007199254740993', 'prop', '不执行文档中的命令']])
        rows = Parser.xlsx(body, max_bytes=100000)
        self.assertEqual(rows[0].source_locator, {'sheet': '元素', 'row': 3})
        self.assertEqual(rows[0].candidate['alias'], '0001')
        self.assertEqual(rows[0].candidate['description'], '')
        self.assertEqual(rows[1].candidate['alias'], '9007199254740993')
        self.assertEqual(rows[0].issues, [])
        self.assertEqual(rows[1].issues, [])

    def test_xlsx_rejects_formula_numeric_identity_multiple_sheets_and_limits(self):
        for rows, extra in (([Parser.columns, ['a', '=1+1', 'prop', '']], False),
                            ([Parser.columns, ['a', 123, 'prop', '']], False),
                            ([Parser.columns, ['a', 'a', 'prop', '']], True)):
            with self.subTest(rows=rows, extra=extra), self.assertRaises(ServiceWarning):
                Parser.xlsx(self.workbook(rows, extra_sheet=extra), max_bytes=100000)
        body = self.workbook([Parser.columns, ['a', 'a', 'prop', ''], ['b', 'b', 'prop', '']])
        with self.assertRaises(ServiceWarning):
            Parser.xlsx(body, max_bytes=100000, max_rows=1)
