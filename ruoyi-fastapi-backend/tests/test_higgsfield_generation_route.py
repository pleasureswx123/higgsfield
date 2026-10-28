"""显式路由状态及并发容量在真实 PostgreSQL 事务中验证。"""

import asyncio
import os
import unittest

from sqlalchemy import text

from exceptions.exception import ServiceWarning
from module_higgsfield.service.generation_route_service import GenerationRouteService
from tests import test_higgsfield_job_storage as storage
from tests import test_higgsfield_model_catalog as catalog


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class GenerationRouteTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = catalog.CatalogTests.cleanup_schema
    job = storage.JobStorageTests.job

    async def asyncSetUp(self) -> None:
        await catalog.CatalogTests.asyncSetUp(self)
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_provider_connection SET status='1'"))
            await db.execute(text("UPDATE hf_provider_credential SET status='1'"))
            await db.execute(
                text(
                    "UPDATE hf_credential_version SET state='1',valid_from=clock_timestamp()-interval '1 day',valid_until=NULL"
                )
            )
            self.key_id = await db.scalar(text('SELECT credential_version_id FROM hf_credential_version LIMIT 1'))
            await db.execute(
                text(
                    "INSERT INTO hf_routing_policy(project_provider_config_id,credential_id,priority,max_concurrency,enabled,create_time,update_time) SELECT config_id,:credential,1,1,'Y',NOW(),NOW() FROM hf_project_provider_config"
                ),
                {'credential': int(self.credential_id)},
            )
            await db.commit()

    async def test_enabled_binding_and_live_expiry(self) -> None:
        async with self.sessions() as db:
            result = await GenerationRouteService.select(db, self.owner, self.project_id, int(self.model_version_id))
            self.assertEqual(result['credentialVersionId'], str(self.key_id))
            self.assertNotIn('secret', str(result))
            await db.rollback()
            await db.execute(text("UPDATE hf_credential_version SET valid_until=clock_timestamp()-interval '1 hour'"))
            await db.commit()
            with self.assertRaises(ServiceWarning):
                await GenerationRouteService.select(db, self.owner, self.project_id, int(self.model_version_id))

    async def test_competing_admission_reads_committed_capacity(self) -> None:
        async with self.sessions() as first:
            await GenerationRouteService.select(first, self.owner, self.project_id, int(self.model_version_id))
            started = asyncio.Event()

            async def contender() -> None:
                async with self.sessions() as second:
                    started.set()
                    with self.assertRaises(ServiceWarning):
                        await GenerationRouteService.select(
                            second, self.owner, self.project_id, int(self.model_version_id)
                        )

            waiting = asyncio.create_task(contender())
            try:
                await started.wait()
                await asyncio.sleep(0.05)
                self.assertFalse(waiting.done())
                first.add(self.job(project_id=self.project_id, credential_version_id=self.key_id))
                await first.commit()
                await asyncio.wait_for(waiting, 10)
            finally:
                if not waiting.done():
                    waiting.cancel()
                    await asyncio.gather(waiting, return_exceptions=True)
