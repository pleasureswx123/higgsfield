"""价格来源不会抓取地址、冒用制作上传或因重试重复记审计。"""

import importlib.util
import os
from pathlib import Path
import unittest
from uuid import uuid4
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from pydantic import ValidationError
from exceptions.exception import ServiceWarning, PermissionException
from module_higgsfield.entity.vo.price_vo import PriceSourceCreate
from module_higgsfield.service.price_source_service import PriceSourceService
from tests import test_higgsfield_price_books as books


class SourceInputTests(unittest.TestCase):
    def test_url_time_and_evidence_validation(self):
        base = dict(sourceType='manual_confirmation', excerpt='人工确认报价', observedAt='2026-01-01T00:00:00Z')
        for changes in (
            {'excerpt': ' '},
            {'sourceUrl': 'javascript:alert(1)'},
            {'sourceUrl': 'https://user:key@example.com/'},
            {'observedAt': '2026-01-01T00:00:00'},
            {'observedAt': '2026-01-01T00:00:00.000001Z'},
            {'sourceType': 'official_screenshot'},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                PriceSourceCreate(**(base | changes))
        self.assertEqual(PriceSourceCreate(**base).observed_at.utcoffset().total_seconds(), 0)


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class PriceSourceTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = books.PriceBookTests.cleanup_schema

    async def asyncSetUp(self):
        await books.PriceBookTests.asyncSetUp(self)
        async with self.engine.begin() as conn:
            for filename in ('20261027_06_assets.py', '20261027_24_price_sources.py'):
                spec = importlib.util.spec_from_file_location(
                    filename[:-3], Path(__file__).resolve().parents[1] / 'alembic/versions' / filename)
                migration = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(migration)

                def execute(sync_conn):
                    with Operations.context(MigrationContext.configure(sync_conn)):
                        migration.upgrade()

                await conn.run_sync(execute)

    def payload(self, **changes):
        return PriceSourceCreate(
            **(
                dict(
                    sourceType='vendor_document',
                    sourceUrl='https://example.com/pricing',
                    excerpt='单价原文',
                    observedAt='2026-01-01T08:00:00+08:00',
                )
                | changes
            )
        )

    async def test_replay_read_and_audit(self):
        key = str(uuid4())
        async with self.sessions() as db:
            result, replay = await PriceSourceService.create(db, self.owner, self.payload(), key)
            self.assertFalse(replay)
            repeated, replay = await PriceSourceService.create(db, self.owner, self.payload(), key)
            self.assertTrue(replay)
            self.assertEqual(result, repeated)
            source = await PriceSourceService.get(db, self.owner, result['data']['id'])
            self.assertEqual(source, result['data'])
            self.assertEqual(
                await db.scalar(text("SELECT count(*) FROM hf_audit_log WHERE object_type='price_source'")), 1
            )
            with self.assertRaises(ServiceWarning):
                await PriceSourceService.create(db, self.owner, self.payload(excerpt='改价'), key)
            self.owner.permissions = []
            with self.assertRaises(PermissionException):
                await PriceSourceService.get(db, self.owner, source['id'])

    async def test_future_and_uncontrolled_upload_leave_no_record(self):
        async with self.sessions() as db:
            for changes in ({'uploadId': '1'}, {'observedAt': '2099-01-01T00:00:00Z'}):
                with self.assertRaises(ServiceWarning):
                    await PriceSourceService.create(db, self.owner, self.payload(**changes), str(uuid4()))
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_price_source')), 0)
