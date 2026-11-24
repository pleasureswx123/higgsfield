"""为隔离的测试 schema 执行用例依赖的真实迁移。"""

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations


async def migrate_connection(conn, *filenames):
    directory = Path(__file__).resolve().parents[1] / 'alembic/versions'

    def upgrade(sync_conn):
        with Operations.context(MigrationContext.configure(sync_conn)):
            for filename in filenames:
                spec = importlib.util.spec_from_file_location(filename[:-3], directory / filename)
                migration = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(migration)
                migration.upgrade()

    await conn.run_sync(upgrade)


async def apply_migrations(engine, *filenames):
    async with engine.begin() as conn:
        await migrate_connection(conn, *filenames)
