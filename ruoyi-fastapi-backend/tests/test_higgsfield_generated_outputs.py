"""输出真实迁移、独立归档约束与批量统计。"""

import importlib.util
import os
from pathlib import Path
import unittest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from module_higgsfield.entity.do.generated_output_do import HfGeneratedOutput
from module_higgsfield.dao.generated_output_dao import GeneratedOutputDao
from module_higgsfield.service.write_service import WriteService
from tests import test_higgsfield_job_storage as storage


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class GeneratedOutputTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = storage.JobStorageTests.cleanup_schema
    migrate = storage.JobStorageTests.migrate

    async def asyncSetUp(self):
        await storage.JobStorageTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location(
            'outputs', Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_33_generated_outputs.py'
        )
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')

    def output(self, **changes):
        return HfGeneratedOutput(
            **(dict(job_id=1, ordinal=0, kind='image', **WriteService.audit(self.owner)) | changes)
        )

    async def test_archive_content_and_unique_constraints(self):
        async with self.sessions() as db:
            db.add(self.output())
            await db.flush()
            for change in (
                {},
                {'ordinal': -1},
                {'ordinal': 1, 'revision': 0},
                {'ordinal': 1, 'archive_state': '2'},
                {'ordinal': 1, 'file_id': 3},
                {'ordinal': 1, 'kind': 'text'},
                {'ordinal': 1, 'kind': 'text', 'archive_state': '5', 'text_content': ''},
                {'ordinal': 1, 'actual_metadata': []},
            ):
                with self.assertRaises(IntegrityError):
                    async with db.begin_nested():
                        db.add(self.output(**change))
                        await db.flush()
            db.add(self.output(ordinal=1, archive_state='2', file_id=3))
            db.add(self.output(ordinal=2, kind='text', archive_state='5', text_content='生成正文'))
            await db.commit()

    async def test_batch_summary_includes_deleted_evidence_and_text(self):
        async with self.sessions() as db:
            for ordinal, state in enumerate(('0', '1', '2', '3', '4', '5')):
                db.add(
                    self.output(
                        ordinal=ordinal,
                        archive_state=state,
                        kind='text' if state == '5' else 'image',
                        text_content='正文' if state == '5' else None,
                        file_id=7 if state == '2' else None,
                        del_flag='2' if state == '4' else '0',
                    )
                )
            db.add(self.output(job_id=2, archive_state='3'))
            await db.flush()
            result = await GeneratedOutputDao.archive_summaries(db, [1, 2, 3])
            self.assertEqual(result[1], dict(total=6, ready=2, failed=2, pending=2))
            self.assertEqual(result[2], dict(total=1, ready=0, failed=1, pending=0))
            self.assertEqual(result[3], dict(total=0, ready=0, failed=0, pending=0))
            self.assertEqual(await GeneratedOutputDao.archive_summaries(db, []), {})

    async def test_comments_no_foreign_keys_and_roundtrip(self):
        async with self.sessions() as db:
            missing = await db.scalar(
                text(
                    "SELECT count(*) FROM pg_attribute a WHERE a.attrelid='hf_generated_output'::regclass AND a.attnum>0 AND NOT a.attisdropped AND col_description(a.attrelid,a.attnum) IS NULL"
                )
            )
            self.assertEqual(missing, 0)
            self.assertEqual(
                await db.scalar(
                    text(
                        "SELECT count(*) FROM pg_constraint WHERE conrelid='hf_generated_output'::regclass AND contype='f'"
                    )
                ),
                0,
            )
        await self.migrate('downgrade')
        await self.migrate('upgrade')
