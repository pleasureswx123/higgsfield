"""真实隔离 PostgreSQL 验证全平台继承、原配置保留和项目权限。"""
import importlib.util
import os
import unittest
from module_higgsfield.dao.credential_dao import CredentialDao
from pathlib import Path
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from exceptions.exception import ServiceWarning, PermissionException
from module_higgsfield.entity.vo.routing_vo import RoutingUpdate
from module_higgsfield.entity.vo.project_vo import ProjectCreate
from module_higgsfield.entity.vo.model_catalog_vo import ModelCatalogQuery
from module_higgsfield.service.project_service import ProjectService
from module_higgsfield.service.model_catalog_service import ModelCatalogService
from module_higgsfield.service.generation_route_service import GenerationRouteService
from module_higgsfield.service.routing_service import RoutingService
from tests import test_higgsfield_generation_route as route_tests


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class PlatformRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_manual_review_image_releases_capacity_but_keeps_credential_dependency(self):
        async with self.sessions() as db:
            row = route_tests.GenerationRouteTests.job(self, project_id=self.project_id, credential_version_id=self.key_id,
                           orchestration_state='3', upstream_state='6', next_action_time=None)
            db.add(row)
            await db.commit()
            self.assertEqual((await CredentialDao.in_flight(db, [self.key_id]))[self.key_id], 1)
            self.assertEqual(await CredentialDao.in_flight(db, [self.key_id], for_admission=True), {})
            selected = await GenerationRouteService.select(db, self.owner, self.project_id, int(self.model_version_id))
            self.assertEqual(selected['credentialVersionId'], str(self.key_id))
            await db.rollback()
            # 仍可自动恢复的图片和结果未知的视频继续占名额。
            await db.execute(text("UPDATE hf_creation_job SET next_action_time=clock_timestamp()"))
            await db.commit()
            self.assertEqual((await CredentialDao.in_flight(db, [self.key_id], for_admission=True))[self.key_id], 1)
            with self.assertRaises(ServiceWarning):
                await GenerationRouteService.select(db, self.owner, self.project_id, int(self.model_version_id))
            await db.rollback()
            await db.execute(text("UPDATE hf_creation_job SET kind='video', next_action_time=NULL"))
            await db.commit()
            self.assertEqual((await CredentialDao.in_flight(db, [self.key_id], for_admission=True))[self.key_id], 1)

    async def test_queue_admission_and_serialized_execution_capacity(self):
        from module_higgsfield.dao.job_lease_dao import JobLeaseDao
        from datetime import timedelta
        async with self.sessions() as db:
            route = await GenerationRouteService.select(db, self.owner, self.project_id, int(self.model_version_id), allow_queue=True)
            first = route_tests.GenerationRouteTests.job(self, project_id=self.project_id, credential_version_id=self.key_id,
                        orchestration_state='0', upstream_state='0', input_snapshot={'route': route})
            second = route_tests.GenerationRouteTests.job(self, project_id=self.project_id, credential_version_id=self.key_id,
                        orchestration_state='0', upstream_state='0', input_snapshot={'route': route})
            first.idempotency_key = str(uuid4())
            second.idempotency_key = str(uuid4())
            db.add_all([first, second])
            await db.commit()
            selected = await GenerationRouteService.select(db, self.owner, self.project_id, int(self.model_version_id), allow_queue=True)
            self.assertEqual(selected['credentialVersionId'], str(self.key_id))
            await db.commit()
            now = await JobLeaseDao.now(db)
            self.assertTrue(await JobLeaseDao.has_execution_capacity(db, first, now))
            # 第二个独立工作器不能同时分配同一凭据。
            async with self.sessions() as other:
                self.assertFalse(await JobLeaseDao.has_execution_capacity(other, second, now))
                await other.rollback()
            first.lease_owner = 'queue-test'
            first.lease_until = now + timedelta(seconds=60)
            await db.commit()
            self.assertFalse(await JobLeaseDao.has_execution_capacity(db, second, now))
            first.orchestration_state = '5'
            first.upstream_state = '3'
            first.lease_owner = first.lease_until = None
            await db.commit()
            self.assertTrue(await JobLeaseDao.has_execution_capacity(db, second, now))
            await db.rollback()

    cleanup_schema = route_tests.GenerationRouteTests.cleanup_schema

    async def test_platform_stop_overrides_existing_project_route_and_can_resume(self):
        async with self.sessions() as db:
            original = await RoutingService.get(db, self.owner, self.project_id)
            config = await RoutingService.get(db, self.owner, None)
            await RoutingService.save(db, self.owner, None,
                RoutingUpdate(revision=config['revision'], routes=original['routes']), str(uuid4()))
            for enabled in (False, True):
                config = await RoutingService.get(db, self.owner, None)
                routes = [{**row, 'enabled': enabled} for row in config['routes']]
                await RoutingService.save(db, self.owner, None,
                    RoutingUpdate(revision=config['revision'], routes=routes), str(uuid4()))
                self.assertEqual(await RoutingService.get(db, self.owner, self.project_id), original)
                result = await ModelCatalogService.listing(db, self.owner,
                    ModelCatalogQuery(projectId=str(self.project_id), kind='image'))
                self.assertEqual(result.total, int(enabled))
                if enabled:
                    route = await GenerationRouteService.select(db, self.owner, self.project_id, int(self.model_version_id))
                    self.assertEqual(route['credentialVersionId'], str(self.key_id))
                else:
                    with self.assertRaises(ServiceWarning):
                        await GenerationRouteService.select(db, self.owner, self.project_id, int(self.model_version_id))
                await db.rollback()

    async def asyncSetUp(self):
        await route_tests.GenerationRouteTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location('platform_migration',
            Path(__file__).resolve().parents[1] / 'alembic/versions/20261102_86_platform_model_routing.py')
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        async with self.engine.begin() as conn:
            def migrate(sync_conn):
                with Operations.context(MigrationContext.configure(sync_conn)):
                    migration.upgrade()
            await conn.run_sync(migrate)

    async def test_existing_and_new_projects_inherit_without_duplicating_routes(self):
        async with self.sessions() as db:
            original = await RoutingService.get(db, self.owner, self.project_id)
            global_config = await RoutingService.get(db, self.owner, None)
            payload = RoutingUpdate(revision=global_config['revision'], routes=original['routes'])
            key = str(uuid4())
            await RoutingService.save(db, self.owner, None, payload, key)
            _, replayed = await RoutingService.save(db, self.owner, None, payload, key)
            self.assertTrue(replayed)
            self.assertEqual(await RoutingService.get(db, self.owner, self.project_id), original)
            # 新项目不生成任何专用路由，但目录与实际任务选择都继承全平台配置。
            created, _ = await ProjectService.create_project(db, self.owner, ProjectCreate(name='自动可用新项目'), str(uuid4()))
            new_id = int(created['data']['id'])
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_project_provider_config WHERE project_id=:id'), {'id': new_id}), 0)
            for project_id in (self.project_id, new_id):
                result = await ModelCatalogService.listing(db, self.owner, ModelCatalogQuery(projectId=str(project_id), kind='image'))
                self.assertEqual(result.total, 1)
                selected = await GenerationRouteService.select(db, self.owner, project_id, int(self.model_version_id))
                self.assertEqual(selected['credentialVersionId'], str(self.key_id))
                await db.rollback()
            # 原有项目清空专用配置后也可直接继承，不要求重新建项目。
            await RoutingService.save(db, self.owner, self.project_id,
                RoutingUpdate(revision=original['revision'], routes=[]), str(uuid4()))
            selected = await GenerationRouteService.select(db, self.owner, self.project_id, int(self.model_version_id))
            self.assertEqual(selected['credentialVersionId'], str(self.key_id))
            await db.rollback()
            for operation in (
                lambda: ModelCatalogService.listing(db, self.other, ModelCatalogQuery(projectId=str(new_id), kind='image')),
                lambda: GenerationRouteService.select(db, self.other, new_id, int(self.model_version_id)),
            ):
                with self.assertRaises((ServiceWarning, PermissionException)):
                    await operation()
                await db.rollback()
            # 平台配置管理权限不等同于项目成员权限。
            self.other.permissions = []
            with self.assertRaises((ServiceWarning, PermissionException)):
                await RoutingService.get(db, self.other, None)
            await db.rollback()
            await db.execute(text("UPDATE hf_project SET status='1' WHERE project_id=:id"), {'id': new_id})
            await db.commit()
            with self.assertRaises(ServiceWarning):
                await GenerationRouteService.select(db, self.owner, new_id, int(self.model_version_id))
