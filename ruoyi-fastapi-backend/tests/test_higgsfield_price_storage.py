"""在隔离 PostgreSQL schema 验证价格迁移及约束。"""

import importlib.util
import os
from pathlib import Path
import unittest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from tests import test_higgsfield_projects as projects


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class PriceStorageTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = projects.ProjectDatabaseTests.cleanup_schema

    async def asyncSetUp(self):
        await projects.ProjectDatabaseTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location(
            'price_migration', Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_22_prices.py'
        )
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')

    async def migrate(self, operation):
        async with self.engine.begin() as conn:

            def execute(sync_conn):
                with Operations.context(MigrationContext.configure(sync_conn)):
                    getattr(self.migration, operation)()

            await conn.run_sync(execute)

    async def test_scope_uniqueness_and_roundtrip(self):
        async with self.sessions() as db:
            insert = "INSERT INTO hf_price_book(model_variant_id,purpose,account_id,currency,price_book_name,create_time,update_time) VALUES(1,:purpose,:account,'CNY','测试价格',NOW(),NOW()) RETURNING price_book_id"
            book = await db.scalar(text(insert), {'purpose': 'platform', 'account': None})
            for values in (
                {'purpose': 'platform', 'account': None},
                {'purpose': 'platform', 'account': 1},
                {'purpose': 'procurement', 'account': None},
            ):
                with self.assertRaises(IntegrityError):
                    async with db.begin_nested():
                        await db.execute(text(insert), values)
            for account in (1, 2):
                await db.execute(text(insert), {'purpose': 'procurement', 'account': account})
            version = await db.scalar(
                text(
                    "INSERT INTO hf_price_version(price_book_id,version_no,rounding_mode,calculation_scale,create_user_id,create_time,update_time) VALUES(:book,1,'half_up',10,1,NOW(),NOW()) RETURNING price_version_id"
                ),
                {'book': book},
            )
            rule = "INSERT INTO hf_price_rule_item(price_version_id,item_code,unit,unit_quantity,unit_price,formula_template,free_reason,create_time,update_time) VALUES(:version,'video_tokens','token',1000000,:price,'linear',:reason,NOW(),NOW()) RETURNING unit_price"
            with self.assertRaises(IntegrityError):
                async with db.begin_nested():
                    await db.execute(text(rule), {'version': version, 'price': 0, 'reason': None})
            price = await db.scalar(text(rule), {'version': version, 'price': 70, 'reason': None})
            self.assertEqual(str(price), '70.0000000000')
            with self.assertRaises(IntegrityError):
                async with db.begin_nested():
                    await db.execute(text(rule), {'version': version, 'price': 70, 'reason': None})
            await db.commit()
        await self.migrate('downgrade')
        await self.migrate('upgrade')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_price_book')), 0)

    async def test_all_fields_commented_without_foreign_keys(self):
        async with self.sessions() as db:
            missing = await db.scalar(
                text(
                    "SELECT count(*) FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=current_schema() AND c.relname IN ('hf_price_book','hf_price_version','hf_price_rule_item') AND a.attnum>0 AND NOT a.attisdropped AND col_description(c.oid,a.attnum) IS NULL"
                )
            )
            self.assertEqual(missing, 0)
            foreign_keys = await db.scalar(
                text(
                    "SELECT count(*) FROM pg_constraint x JOIN pg_class c ON c.oid=x.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=current_schema() AND c.relname IN ('hf_price_book','hf_price_version','hf_price_rule_item') AND x.contype='f'"
                )
            )
            self.assertEqual(foreign_keys, 0)
