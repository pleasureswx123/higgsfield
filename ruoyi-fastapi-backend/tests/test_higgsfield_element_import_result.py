"""导入候选登记的并发去重、重试不覆盖人工编辑与失败原子回滚。"""
import asyncio
import os
import unittest
from unittest.mock import patch
from sqlalchemy import text
from exceptions.exception import ServiceWarning
from module_higgsfield.entity.do.element_import_do import HfImportJob
from module_higgsfield.dao.element_import_dao import ElementImportDao
from module_higgsfield.service.element_import_parser_service import ElementImportParserService as Parser
from module_higgsfield.service.element_import_result_service import ElementImportResultService as Result
from tests import test_higgsfield_element_import_storage as storage


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ElementImportResultTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = storage.ElementImportStorageTests.cleanup_schema
    migrate = storage.ElementImportStorageTests.migrate

    async def asyncSetUp(self):
        await storage.ElementImportStorageTests.asyncSetUp(self)
        async with self.sessions() as db:
            job = HfImportJob(project_id=1, actor_id=1, source_file_id=1, schema_version=1,
                source_format='csv', parser_version=Parser.version, idempotency_key='a' * 64, **self.audit)
            db.add(job)
            await db.flush()
            self.identity = job.import_id
            await db.commit()
        self.rows = Parser.csv('名称,别名,分类,描述\n角色,001,角色,说明\n,002,场景,待补名称'.encode(), max_bytes=10000)

    async def apply(self, rows=None, source_file_id=1):
        async with self.sessions() as db:
            return await Result.apply(db, self.identity, self.rows if rows is None else rows,
                                      source_file_id=source_file_id, parser_version=Parser.version)

    async def test_concurrent_registration_and_replay_preserve_edited_candidate(self):
        results = await asyncio.gather(self.apply(), self.apply())
        self.assertEqual(sorted(results), [False, True])
        async with self.sessions() as db:
            report = await db.scalar(text('SELECT validation_report FROM hf_import_job'))
            self.assertEqual((report['total'], report['valid'], report['invalid']), (2, 1, 1))
            self.assertEqual(await db.scalar(text('SELECT revision FROM hf_import_job')), 2)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_import_row')), 2)
            rows = (await db.execute(text('SELECT state,error_code,issues FROM hf_import_row ORDER BY row_no'))).all()
            self.assertEqual(rows[0], ('0', None, []))
            self.assertEqual(rows[1][0:2], ('2', 'ELEMENT_FIELD_INVALID'))
            await db.execute(text("UPDATE hf_import_row SET candidate=jsonb_set(candidate,'{name}','\"人工修正\"'),revision=2 WHERE row_no=1"))
            await db.commit()
        self.assertFalse(await self.apply())
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text("SELECT candidate->>'name' FROM hf_import_row WHERE row_no=1")), '人工修正')
        changed = Parser.csv(b'name,alias,category,description\na,other,prop,text', max_bytes=10000)
        with self.assertRaises(ServiceWarning):
            await self.apply(changed)
        with self.assertRaises(ServiceWarning):
            await self.apply(source_file_id=2)

    async def test_candidate_write_failure_rolls_back_all_rows(self):
        original = ElementImportDao.add_rows

        async def interrupted(db, rows):
            await original(db, rows)
            raise RuntimeError('模拟候选写入后故障')

        with patch.object(ElementImportDao, 'add_rows', interrupted), self.assertRaises(RuntimeError):
            await self.apply()
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_import_row')), 0)
            self.assertEqual(await db.scalar(text('SELECT status FROM hf_import_job')), '0')
            self.assertEqual(await db.scalar(text('SELECT revision FROM hf_import_job')), 1)
        self.assertTrue(await self.apply())

    async def test_diagnostics_cannot_be_removed_and_summary_is_bounded(self):
        self.rows[1].issues.clear()
        with self.assertRaises(ServiceWarning):
            await self.apply()
        rows = Parser.csv(('名称,别名,分类,描述\n' + '\n'.join(f',id{i},未知,说明' for i in range(150))).encode(),
                          max_bytes=100000)
        self.assertTrue(await self.apply(rows))
        async with self.sessions() as db:
            report = await db.scalar(text('SELECT validation_report FROM hf_import_job'))
            self.assertEqual(report['invalid'], 150)
            self.assertEqual(len(report['errors']), 100)
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM hf_import_row WHERE jsonb_array_length(issues)>0")), 150)
