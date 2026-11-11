"""在隔离 PostgreSQL schema 验证真实迁移，全程事务回滚。"""
import importlib.util
import os
from pathlib import Path
import unittest
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from config.database import DataSourceRegistry


@unittest.skipUnless(os.environ.get('HF_REVIEW_DB_TEST') == '1', '需要显式启用本地数据库验收')
class ReviewMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_migration_preserves_legacy_and_enforces_version(self):
        engine = DataSourceRegistry.get_async_engine()
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.run_sync(self.verify_migration)
            finally:
                await transaction.rollback()
        await engine.dispose()

    def verify_migration(self, connection):
        schema = 'hf_review_test_' + uuid4().hex
        connection.execute(text(f'CREATE SCHEMA {schema}'))
        connection.execute(text(f'SET LOCAL search_path TO {schema}'))
        connection.execute(text('CREATE TABLE hf_asset (asset_id bigserial PRIMARY KEY)'))
        connection.execute(text('CREATE TABLE hf_review_event (review_event_id bigserial PRIMARY KEY, '
                                'element_id bigint, output_id bigint, '
                                'CONSTRAINT ck_hf_review_target CHECK(num_nonnulls(element_id,output_id)=1))'))
        connection.execute(text('INSERT INTO hf_review_event (element_id) VALUES (1)'))
        path = Path(__file__).parents[1] / 'alembic/versions/20261111_92_version_review.py'
        spec = importlib.util.spec_from_file_location('review_migration', path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            legacy = connection.execute(text('SELECT action,element_revision_id FROM hf_review_event')).one()
            self.assertEqual(tuple(legacy), ('legacy', None))
            # 新审核不能缺版本，也不能把元素修订错挂到素材。
            for sql in (
                "INSERT INTO hf_review_event (asset_id,action) VALUES (1,'approve')",
                "INSERT INTO hf_review_event (asset_id,element_revision_id,action) VALUES (1,2,'approve')",
            ):
                with self.assertRaises(IntegrityError), connection.begin_nested():
                    connection.execute(text(sql))
            connection.execute(text("INSERT INTO hf_review_event (asset_id,asset_version_id,action) VALUES (1,2,'approve')"))
            with self.assertRaisesRegex(RuntimeError, '不能回滚'):
                migration.downgrade()
