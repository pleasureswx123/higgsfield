"""外部调用事实的真实迁移、状态约束与注释校验。"""

import importlib.util
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from module_higgsfield.entity.do.provider_call_do import HfProviderCall
from module_higgsfield.service.write_service import WriteService
from tests import test_higgsfield_job_storage as storage

MIGRATION = Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_35_provider_calls.py'


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ProviderCallStorageTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = storage.JobStorageTests.cleanup_schema
    migrate = storage.JobStorageTests.migrate

    async def asyncSetUp(self) -> None:
        await storage.JobStorageTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location('calls_migration', MIGRATION)
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')

    def call(self, **changes) -> HfProviderCall:
        return HfProviderCall(
            **(
                {
                    'job_id': 1,
                    'account_id': 1,
                    'credential_version_id': 1,
                    'operation': 'video_poll',
                    'request_hash': 'a' * 64,
                    'request_metadata': {'connectionVersionId': '1'},
                    **WriteService.audit(self.owner),
                }
                | changes
            )
        )

    async def test_separate_calls_and_state_evidence(self) -> None:
        async with self.sessions() as db:
            first, second = self.call(), self.call()
            db.add_all([first, second])
            await db.commit()
            self.assertNotEqual(first.call_id, second.call_id)
            self.assertEqual(first.state, '0')
            first.state = '1'
            first.started_time = datetime.now(timezone.utc)
            await db.commit()
            first.state = '3'
            first.finished_time = first.started_time + timedelta(seconds=1)
            await db.commit()
            self.assertEqual(first.acceptance, 'unknown')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 2)

    async def test_invalid_scope_state_and_metadata_rejected(self) -> None:
        now = datetime.now(timezone.utc)
        for changes in (
            {'job_id': None},
            {'cost_center_id': 2},
            {'http_status': 99},
            {'request_metadata': []},
            {'request_hash': 'not-a-hash'},
            {'operation': 'unknown_api'},
            {'state': '1'},
            {'state': '3', 'started_time': now, 'finished_time': now, 'acceptance': 'accepted'},
            {'state': '2', 'started_time': now, 'finished_time': now - timedelta(seconds=1)},
        ):
            async with self.sessions() as db:
                with self.subTest(changes=changes), self.assertRaises(IntegrityError):
                    db.add(self.call(**changes))
                    await db.commit()
                await db.rollback()
        async with self.sessions() as db:
            missing = await db.scalar(
                text(
                    "SELECT count(*) FROM pg_attribute WHERE attrelid='hf_provider_call'::regclass AND attnum>0 AND NOT attisdropped AND col_description(attrelid,attnum) IS NULL"
                )
            )
            self.assertEqual(missing, 0)
            foreign_keys = await db.scalar(
                text("SELECT count(*) FROM pg_constraint WHERE conrelid='hf_provider_call'::regclass AND contype='f'")
            )
            self.assertEqual(foreign_keys, 0)
