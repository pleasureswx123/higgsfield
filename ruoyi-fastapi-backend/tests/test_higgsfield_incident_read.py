"""异常队列按授权与真实状态筛选，不以故障查询泄露输入内容。"""
import importlib.util
import os
import unittest
from pathlib import Path
from sqlalchemy import text
from alembic.migration import MigrationContext
from alembic.operations import Operations
from exceptions.exception import ServiceWarning
from tests import test_higgsfield_provider_call_read as calls
from module_higgsfield.entity.vo.incident_query_vo import IncidentQuery
from module_higgsfield.service.incident_read_service import IncidentReadService


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class IncidentReadTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = calls.ProviderCallReadTests.cleanup_schema
    create = calls.ProviderCallReadTests.create
    scope = calls.ProviderCallReadTests.scope
    job = calls.ProviderCallReadTests.job
    call = calls.ProviderCallReadTests.call

    async def asyncSetUp(self):
        await calls.ProviderCallReadTests.asyncSetUp(self)
        async with self.engine.begin() as conn:
            spec = importlib.util.spec_from_file_location('incident_output_migration', Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_33_generated_outputs.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            def migrate(sync):
                with Operations.context(MigrationContext.configure(sync)):
                    module.upgrade()
            await conn.run_sync(migrate)
            await conn.execute(text("UPDATE hf_creation_job SET orchestration_state='3' WHERE job_id=:id"), {'id': self.job_id})

    async def listing(self, **values):
        async with self.sessions() as db:
            return await IncidentReadService.listing(db, self.actor, IncidentQuery(**values))

    async def test_scope_unknown_recovery_and_evidence(self):
        self.assertEqual((await self.listing()).total, 0)
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await IncidentReadService.detail(db, self.actor, self.job_id)
        await self.scope('4')
        page = await self.listing(projectId=str(self.project_id), state='submission_unknown')
        self.assertEqual(page.total, 1)
        row = page.rows[0]
        self.assertEqual(row['evidenceRefs'], [f'provider-call:{self.call_id}'])
        self.assertEqual(row['allowedActions'], [])
        self.assertEqual(row['archiveSummary']['total'], 0)
        self.assertNotIn('inputSnapshot', row)
        self.assertEqual((await self.listing(state='blocked')).total, 0)
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_creation_job SET orchestration_state='5',upstream_state='3'"))
            await db.commit()
            detail = await IncidentReadService.detail(db, self.actor, self.job_id)
            self.assertEqual(detail['upstreamState'], 'succeeded')
        self.assertEqual((await self.listing()).total, 0)

    async def test_archive_failure_and_deleted_output_boundary(self):
        await self.scope('1')
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_creation_job SET orchestration_state='5',upstream_state='3'"))
            await db.execute(text("""INSERT INTO hf_generated_output(job_id,ordinal,kind,archive_state,create_time,update_time)
                VALUES (:id,0,'image','3',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP),
                (:id,1,'image','4',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"""), {'id': self.job_id})
            await db.commit()
        page = await self.listing(state='archive_failed', pageSize=1)
        self.assertEqual(page.total, 1)
        self.assertEqual(page.rows[0]['archiveSummary']['failed'], 2)
        self.assertEqual((await self.listing(state='source_expired')).total, 1)
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_generated_output SET del_flag='2'"))
            await db.commit()
        self.assertEqual((await self.listing()).total, 0)
