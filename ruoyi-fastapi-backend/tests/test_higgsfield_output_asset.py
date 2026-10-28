"""作品入库的真实事务、来源追溯与授权边界。"""
import asyncio
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4
from sqlalchemy import text
from exceptions.exception import PermissionException, ServiceWarning
from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.entity.do.audit_do import HfAuditLog
from module_higgsfield.entity.vo.asset_vo import OutputToAsset
from module_higgsfield.service.output_asset_service import OutputAssetService as Service
from tests import test_higgsfield_output_read as output_read


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class OutputAssetTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = output_read.OutputReadTests.cleanup_schema
    migrate = output_read.OutputReadTests.migrate
    job = output_read.OutputReadTests.job
    output = output_read.OutputReadTests.output
    create = output_read.OutputReadTests.create
    ready = output_read.OutputReadTests.ready

    async def asyncSetUp(self):
        await output_read.OutputReadTests.asyncSetUp(self)
        for name in ('20261027_04_folders.py', '20261027_16_audit.py'):
            spec = importlib.util.spec_from_file_location('output_asset_migration',
                Path(__file__).resolve().parents[1] / 'alembic/versions' / name)
            self.migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.migration)
            await self.migrate('upgrade')
        async with self.sessions() as db:
            self.project_id = str(await db.scalar(text('SELECT project_id FROM hf_creation_job LIMIT 1')))
            for permission in ('asset:create', 'asset:reference'):
                await db.execute(text("INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope) SELECT role_id,:permission,'project' FROM hf_project_role WHERE code='owner' ON CONFLICT DO NOTHING"), {'permission': permission})
            await db.commit()
        self.payload = OutputToAsset(projectId=self.project_id, name='生成参考图')

    async def convert(self, key=None, payload=None):
        async with self.sessions() as db:
            db.autoflush = False
            return await Service.create(db, self.owner, self.identity, payload or self.payload, key or str(uuid4()))

    async def test_shared_file_source_and_concurrent_idempotence(self):
        await self.ready()
        key = str(uuid4())
        results = await asyncio.gather(self.convert(key), self.convert(key), return_exceptions=True)
        successes = []
        for result in results:
            if isinstance(result, ServiceWarning):
                self.assertEqual(result.data['errorCode'], 'IDEMPOTENCY_IN_PROGRESS')
            else:
                self.assertNotIsInstance(result, BaseException)
                successes.append(result)
        self.assertTrue(successes)
        replay, repeated = await self.convert(key)
        self.assertTrue(repeated)
        for result, _ in successes:
            self.assertEqual(result, replay)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_asset')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_stored_file')), 1)
            version = (await db.execute(text('SELECT file_id,source_output_id FROM hf_asset_version'))).one()
            self.assertEqual(tuple(version), (self.file_id, self.identity))
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_folder_entry WHERE asset_id IS NOT NULL')), 1)
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM hf_audit_log WHERE action='from_output'")), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_generated_output')), 1)
        with self.assertRaises(ServiceWarning):
            await self.convert(key, OutputToAsset(projectId=self.project_id, name='不同请求'))

    async def test_unready_and_missing_reference_permission_block_creation_and_replay(self):
        with self.assertRaises(ServiceWarning):
            await self.convert()
        await self.ready()
        key = str(uuid4())
        await self.convert(key)
        async with self.sessions() as db:
            await db.execute(text("DELETE FROM hf_project_role_permission WHERE permission_code='asset:reference'"))
            await db.commit()
        with self.assertRaises(PermissionException):
            await self.convert(key)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_asset')), 1)

    async def test_invalid_folder_and_audit_failure_leave_no_partial_asset(self):
        await self.ready()
        with self.assertRaises(ServiceWarning):
            await self.convert(payload=OutputToAsset(projectId=self.project_id, name='错误目录', folderId='999999'))
        original = AssetDao.add
        async def fail_audit(db, model, **fields):
            if model is HfAuditLog:
                raise RuntimeError('模拟审计失败')
            return await original(db, model, **fields)
        with patch.object(AssetDao, 'add', side_effect=fail_audit):
            with self.assertRaises(RuntimeError):
                await self.convert()
        async with self.sessions() as db:
            for table in ('hf_asset', 'hf_asset_version', 'hf_folder_entry'):
                self.assertEqual(await db.scalar(text(f'SELECT count(*) FROM {table}')), 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_stored_file')), 1)

    async def test_destination_permission_and_archived_project_block_writes(self):
        await self.ready()
        async with self.sessions() as db:
            await db.execute(text("DELETE FROM hf_project_role_permission WHERE permission_code='asset:create'"))
            await db.commit()
        with self.assertRaises(PermissionException):
            await self.convert()
        async with self.sessions() as db:
            await db.execute(text("INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope) SELECT role_id,'asset:create','project' FROM hf_project_role WHERE code='owner'"))
            await db.execute(text("UPDATE hf_project SET status='2',archived_time=CURRENT_TIMESTAMP WHERE project_id=:id"), {'id': int(self.project_id)})
            await db.commit()
        with self.assertRaises(ServiceWarning) as failure:
            await self.convert()
        self.assertEqual(failure.exception.data['errorCode'], 'PROJECT_READ_ONLY')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_asset')), 0)

    async def test_cross_project_copy_keeps_source_and_rechecks_source_membership(self):
        """目标有创建权限不替代源项目访问权，重放也不能绕过撤权。"""
        await self.ready()
        destination, _ = await self.create(name='跨项目入库目标')
        target_id = destination['data']['id']
        payload = OutputToAsset(projectId=target_id, name='独立素材')
        async with self.sessions() as db:
            before_job = dict((await db.execute(text('SELECT * FROM hf_creation_job LIMIT 1'))).mappings().one())
            before_output = dict((await db.execute(text('SELECT * FROM hf_generated_output LIMIT 1'))).mappings().one())
        key = str(uuid4())
        created, repeated = await self.convert(key, payload)
        self.assertFalse(repeated)
        async with self.sessions() as db:
            row = (await db.execute(text(
                'SELECT s.project_id, v.file_id, v.source_output_id FROM hf_asset a '
                'JOIN hf_asset_space s ON s.space_id=a.space_id '
                'JOIN hf_asset_version v ON v.version_id=a.current_version_id '
                'WHERE a.asset_id=:id'), {'id': int(created['data']['id'])})).one()
            self.assertEqual(tuple(row), (int(target_id), self.file_id, self.identity))
            self.assertEqual(dict((await db.execute(text('SELECT * FROM hf_creation_job LIMIT 1'))).mappings().one()), before_job)
            self.assertEqual(dict((await db.execute(text('SELECT * FROM hf_generated_output LIMIT 1'))).mappings().one()), before_output)
            await db.execute(text("UPDATE hf_project_member SET status='1' WHERE project_id=:id"), {'id': int(self.project_id)})
            await db.commit()
        for request_key in (key, str(uuid4())):
            with self.assertRaises((PermissionException, ServiceWarning)):
                await self.convert(request_key, payload)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_asset')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_asset_version')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_stored_file')), 1)
