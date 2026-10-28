"""标准 CSV 解析保留金额精度、供应商稳定键及重复行证据。"""
import unittest
import io
from openpyxl import Workbook
from decimal import Decimal
from exceptions.exception import ServiceWarning
from module_higgsfield.service.reconciliation_parser_service import ReconciliationParserService as Parser


class ReconciliationParserTests(unittest.TestCase):
    @staticmethod
    def workbook(values, extra_sheet=False):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(list(Parser.columns))
        for row in values:
            sheet.append(row)
        if extra_sheet:
            workbook.create_sheet('另一个账单')
        buffer = io.BytesIO()
        workbook.save(buffer)
        workbook.close()
        return buffer.getvalue()

    def test_xlsx_text_precision_and_physical_rows(self):
        rows = Parser.xlsx(self.workbook([['0000123', 'USD', '0.0000000001'],
            [None, None, None], ['0000123', 'USD', '-1.25']]), 65536)
        self.assertEqual([row.line_no for row in rows], [2, 4])
        self.assertEqual(rows[0].external_line_key, '0000123')
        self.assertEqual(rows[0].amount, Decimal('0.0000000001'))
        self.assertEqual(rows[1].raw_line['amount'], '-1.25')

    def test_xlsx_rejects_numeric_formula_multisheet_and_limits(self):
        for values in ([['0001', 'USD', 1.25]], [[1, 'USD', '1.25']], [['key', 'USD', '=1+2']]):
            with self.subTest(values=values), self.assertRaises(ServiceWarning):
                Parser.xlsx(self.workbook(values), 65536)
        with self.assertRaises(ServiceWarning):
            Parser.xlsx(self.workbook([['key', 'USD', '1']], extra_sheet=True), 65536)
        with self.assertRaises(ServiceWarning):
            Parser.xlsx(self.workbook([['key', 'USD', '1'], ['next', 'USD', '2']]), 65536, max_rows=1)
        with self.assertRaises(ServiceWarning):
            Parser.xlsx(b'not a workbook', 65536)

    def test_exact_values_and_duplicate_evidence(self):
        body = b'\xef\xbb\xbfexternalLineKey,currency,amount\r\n0000123,USD,0.0000000001\r\n\r\n0000123,USD,-1.25\r\n'
        rows = Parser.csv(body, 4096)
        self.assertEqual([row.line_no for row in rows], [2, 4])
        self.assertEqual([row.external_line_key for row in rows], ['0000123', '0000123'])
        self.assertEqual(rows[0].amount, Decimal('0.0000000001'))
        self.assertEqual(rows[1].amount, Decimal('-1.25'))
        self.assertEqual(rows[0].raw_line['amount'], '0.0000000001')

    def test_invalid_money_schema_and_limits(self):
        for amount in ('NaN', 'Infinity', '1e3', '1.00000000001', '100000000000000', '', ' 1', '+1', '01'):
            with self.subTest(amount=amount), self.assertRaises(ServiceWarning):
                Parser.row(2, ['stable-key', 'USD', amount])
        for values in ([' key', 'USD', '1'], ['key', 'usd', '1'], ['key', 'USD', 1.5], ['', 'USD', '1']):
            with self.assertRaises(ServiceWarning):
                Parser.row(2, values)
        for body in (b'amount,currency,externalLineKey\n1,USD,key', b'externalLineKey,currency,amount\n', b'\xff'):
            with self.assertRaises(ServiceWarning):
                Parser.csv(body, 4096)
        body = b'externalLineKey,currency,amount\na,USD,1\nb,USD,2\n'
        with self.assertRaises(ServiceWarning):
            Parser.csv(body, len(body)-1)
        with self.assertRaises(ServiceWarning):
            Parser.csv(body, 4096, max_rows=1)
