"""恢复序列检查覆盖未调用状态、边界及真实隔离数据库。"""

import os
import unittest
from sqlalchemy import text
from module_higgsfield.dao.recovery_sequence_dao import RecoverySequenceDao
from module_higgsfield.service.recovery_sequence_service import RecoverySequenceService
from tests import test_higgsfield_output_read as reads


class SequenceBoundaryTests(unittest.TestCase):
    def test_next_value_respects_called_flag_and_bigint_limit(self):
        row = dict(sequence_name='test', seqincrement=1, seqcycle=False,
                   last_value=1, is_called=False, max_id=None, seqmax=9223372036854775807)
        self.assertIsNone(RecoverySequenceService.reason(row))
        self.assertEqual(RecoverySequenceService.reason(row | {'max_id': 1}), 'sequence_behind')
        self.assertIsNone(RecoverySequenceService.reason(row | {'max_id': 1, 'is_called': True}))
        self.assertEqual(RecoverySequenceService.reason(row | {'sequence_name': None}), 'missing_sequence')
        for policy in ({'seqincrement': -1}, {'seqcycle': True}):
            self.assertEqual(RecoverySequenceService.reason(row | policy), 'unsupported_sequence_policy')
        self.assertEqual(RecoverySequenceService.reason(row | {
            'last_value': row['seqmax'], 'is_called': True}), 'sequence_exhausted')


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class RecoverySequenceDatabaseTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = reads.OutputReadTests.cleanup_schema
    migrate = reads.OutputReadTests.migrate
    job = reads.OutputReadTests.job
    output = reads.OutputReadTests.output
    create = reads.OutputReadTests.create
    asyncSetUp = reads.OutputReadTests.asyncSetUp

    async def test_detects_sequence_behind_without_advancing_or_repairing(self):
        async with self.sessions() as db:
            name = await db.scalar(text("SELECT pg_get_serial_sequence('hf_stored_file','file_id')"))
            maximum = await db.scalar(text('SELECT max(file_id) FROM hf_stored_file'))
            self.assertGreaterEqual(maximum, 1)
            # 仅在测试独有schema中模拟导入数据后遗漏序列恢复。
            await db.execute(text('SELECT setval(CAST(:name AS regclass),:value,false)'),
                             {'name': name, 'value': maximum})
            await db.commit()
        for _ in range(2):
            report = await RecoverySequenceService.audit(self.sessions)
            self.assertIn({'table': 'hf_stored_file', 'column': 'file_id', 'reason': 'sequence_behind'},
                          report['failures'])
        async with self.sessions() as db:
            rows = await RecoverySequenceDao.inventory(db)
            state = next(row for row in rows if row['table_name'] == 'hf_stored_file')
            self.assertEqual(state['last_value'], maximum)
            self.assertFalse(state['is_called'])
            await db.execute(text('SELECT setval(CAST(:name AS regclass),:value,true)'),
                             {'name': name, 'value': maximum})
            await db.commit()
        report = await RecoverySequenceService.audit(self.sessions)
        self.assertFalse(any(row['table'] == 'hf_stored_file' for row in report['failures']))
        self.assertGreater(report['total'], 1)
