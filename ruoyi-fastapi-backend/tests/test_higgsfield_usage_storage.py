"""计费对象去重、未知用量及不可重复修订的真实迁移约束。"""

import importlib.util
import os
import unittest
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from module_higgsfield.entity.do.usage_do import HfBillingSubject, HfUsageRecord
from tests import test_higgsfield_job_storage as storage


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class UsageStorageTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = storage.JobStorageTests.cleanup_schema
    migrate = storage.JobStorageTests.migrate

    async def asyncSetUp(self):
        await storage.JobStorageTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location(
            'usage_records', Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_38_usage_records.py'
        )
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')
        now = datetime.now(UTC)
        self.audit = dict(create_time=now, update_time=now, create_by='test', update_by='test')

    async def test_identity_scope_and_unique_provider_object(self):
        values = dict(
            account_id=1,
            job_id=2,
            origin_call_id=3,
            subject_kind='generation',
            provider_object_id='provider-job',
            identity_key='call:3',
            **self.audit,
        )
        async with self.sessions() as db:
            db.add(HfBillingSubject(**values))
            await db.flush()
            for changes in (
                {'origin_call_id': 4, 'identity_key': 'call:4'},
                {'provider_object_id': None, 'origin_call_id': 4},
                {'cost_center_id': 4},
                {'job_id': None},
            ):
                with self.assertRaises(IntegrityError):
                    async with db.begin_nested():
                        db.add(HfBillingSubject(**(values | changes)))
                        await db.flush()
            db.add(HfBillingSubject(**(values | {'account_id': 2, 'origin_call_id': 5, 'identity_key': 'call:5'})))
            await db.flush()
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_billing_subject')), 2)

    async def test_unknown_is_null_and_duplicate_payload_is_not_new_usage(self):
        values = dict(
            subject_id=1,
            call_id=3,
            revision_no=1,
            completeness='unknown',
            source_path='choices[0].message.content.usage',
            parser_version='image-v1',
            is_cumulative='N',
            payload_hash='a' * 64,
            raw_usage={},
            **self.audit,
        )
        async with self.sessions() as db:
            db.add(HfUsageRecord(**values))
            await db.flush()
            self.assertIsNone(await db.scalar(text('SELECT input_tokens FROM hf_usage_record')))
            for changes in (
                {'revision_no': 2},
                {'payload_hash': 'b' * 64},
                {'revision_no': 2, 'payload_hash': 'b' * 64, 'output_tokens': -1},
            ):
                with self.assertRaises(IntegrityError):
                    async with db.begin_nested():
                        db.add(HfUsageRecord(**(values | changes)))
                        await db.flush()
            for table in ('hf_billing_subject', 'hf_usage_record'):
                self.assertEqual(
                    await db.scalar(
                        text(
                            "SELECT count(*) FROM pg_constraint WHERE conrelid=CAST(:name AS regclass) AND contype='f'"
                        ),
                        {'name': table},
                    ),
                    0,
                )
                self.assertEqual(
                    await db.scalar(
                        text(
                            'SELECT count(*) FROM pg_attribute WHERE attrelid=CAST(:name AS regclass) AND attnum>0 AND NOT attisdropped AND col_description(attrelid,attnum) IS NULL'
                        ),
                        {'name': table},
                    ),
                    0,
                )
