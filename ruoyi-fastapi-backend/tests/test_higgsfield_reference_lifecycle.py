"""真实隔离数据库验证目录整理不漂移引用、素材回收阻止发送；不调用供应商。"""
import hashlib
import importlib.util
import os
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from exceptions.exception import ServiceWarning
from module_higgsfield.dao.generation_accept_dao import GenerationAcceptDao
from module_higgsfield.entity.do.job_do import HfCreationJob
from module_higgsfield.service.generation_access_service import GenerationAccessService
from module_higgsfield.service.job_lease_service import JobLease
from module_higgsfield.service.provider_job_binding_service import ProviderJobBindingService
from module_higgsfield.service.provider_submit_intent_service import ProviderSubmitIntentService
from module_higgsfield.service.reference_compile_service import ReferenceCompileService
from module_higgsfield.service.write_service import WriteService
from tests import test_higgsfield_asset_lifecycle as asset_lifecycle
from tests import test_higgsfield_folders as folders
from tests import test_higgsfield_job_storage as job_storage
from tests.test_higgsfield_reference_compile import payload, ref
from utils.time_util import TimezoneUtil


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ReferenceLifecycleTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = asset_lifecycle.AssetLifecycleTests.cleanup_schema
    create = asset_lifecycle.AssetLifecycleTests.create
    new_upload = asset_lifecycle.AssetLifecycleTests.new_upload
    send_part = asset_lifecycle.AssetLifecycleTests.send_part
    ready_upload = asset_lifecycle.AssetLifecycleTests.ready_upload
    mutate = asset_lifecycle.AssetLifecycleTests.mutate
    folder = folders.FolderDatabaseTests.folder
    action = folders.FolderDatabaseTests.action
    job = job_storage.JobStorageTests.job

    async def asyncSetUp(self):
        await asset_lifecycle.AssetLifecycleTests.asyncSetUp(self)
        self.project_id = int(self.project_id)
        async with self.engine.begin() as conn:
            for filename in ('20261027_29_jobs_outbox.py', '20261027_35_provider_calls.py'):
                spec = importlib.util.spec_from_file_location('reference_lifecycle', Path(__file__).resolve().parents[1] / 'alembic/versions' / filename)
                migration = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(migration)
                def migrate(sync):
                    with Operations.context(MigrationContext.configure(sync)):
                        migration.upgrade()
                await conn.run_sync(migrate)
            await conn.execute(text("INSERT INTO sys_role VALUES(1,'admin','0','0')"))
            await conn.execute(text('INSERT INTO sys_user_role VALUES(1,1)'))
        self.source = await self.folder('引用所在目录')
        self.target = await self.folder('目标目录')
        self.input = payload([ref(version=self.asset['currentVersionId'])])
        async with self.sessions() as db:
            await db.execute(text('UPDATE hf_folder_entry SET folder_id=:folder WHERE asset_id=:asset'), {'folder': int(self.source['id']), 'asset': int(self.asset['id'])})
            compiled = await ReferenceCompileService.resolve(db, self.owner, int(self.project_id), self.input, {'reference_image': ('image',)})
            fixture = self.job(project_id=int(self.project_id), input_snapshot={'compiled': compiled}, orchestration_state='1', lease_owner='reference-test', lease_until=TimezoneUtil.utc_now() + timedelta(minutes=5), fencing_token=1)
            values = {column.name: getattr(fixture, column.name) for column in HfCreationJob.__table__.columns if getattr(fixture, column.name) is not None}
            audit = WriteService.audit(self.owner)
            for key in audit:
                values.pop(key, None)
            job = await GenerationAcceptDao.create(db, values, compiled, audit)
            self.job_id = job.job_id
            self.lease = JobLease(job.job_id, 'reference-test', 1, job.revision, 'prepare')
            await db.commit()
        self.before = await self.evidence()

    async def evidence(self):
        async with self.sessions() as db:
            snapshot = await db.scalar(text('SELECT input_snapshot FROM hf_creation_job WHERE job_id=:id'), {'id': self.job_id})
            refs = (await db.execute(text('SELECT to_jsonb(r) FROM hf_job_reference r WHERE job_id=:id ORDER BY ordinal'), {'id': self.job_id})).scalars().all()
            file = (await db.execute(text('SELECT f.storage_key,f.sha256 FROM hf_asset_version v JOIN hf_stored_file f USING(file_id) WHERE v.version_id=:id'), {'id': int(self.asset['currentVersionId'])})).one()
            with self.storage.open_key(file.storage_key) as stream:
                digest = hashlib.sha256(stream.read()).hexdigest()
            self.assertEqual(digest, file.sha256)
            return snapshot, refs, digest

    async def test_directory_move_copy_recycle_restore_preserve_history(self):
        moved, _ = await self.action(self.source, 'move', {'parentId': self.target['id']})
        self.assertEqual(await self.evidence(), self.before)
        copied, _ = await self.action(moved['data'], 'copy', {'targetParentId': None})
        async with self.sessions() as db:
            copy = (await db.execute(text('SELECT a.asset_id,v.version_id,v.file_id,v.source_asset_version_id FROM hf_folder_entry e JOIN hf_asset a USING(asset_id) JOIN hf_asset_version v ON v.version_id=a.current_version_id WHERE e.folder_id=:id'), {'id': int(copied['data']['id'])})).one()
            self.assertNotEqual(str(copy.asset_id), self.asset['id'])
            self.assertNotEqual(str(copy.version_id), self.asset['currentVersionId'])
            self.assertEqual(str(copy.source_asset_version_id), self.asset['currentVersionId'])
            self.assertEqual(str(copy.file_id), self.before[0]['compiled']['media'][0]['fileId'])
        self.assertEqual(await self.evidence(), self.before)
        deleted, _ = await self.action(moved['data'], 'delete')
        self.assertEqual(await self.evidence(), self.before)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT folder_id FROM hf_folder_entry WHERE asset_id=:id'), {'id': int(self.asset['id'])}), int(self.target['id']))
            self.assertEqual(await db.scalar(text('SELECT del_flag FROM hf_asset WHERE asset_id=:id'), {'id': int(self.asset['id'])}), '0')
        restored, _ = await self.action(deleted['data'], 'restore')
        self.assertEqual(restored['data']['id'], self.source['id'])
        self.assertEqual(await self.evidence(), self.before)
        async with self.sessions() as db:
            await GenerationAccessService.require(db, await db.get(HfCreationJob, self.job_id))
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 0)

    async def test_recycled_reference_blocks_queued_submission_without_paid_call(self):
        async with self.sessions() as db:
            await GenerationAccessService.require(db, await db.get(HfCreationJob, self.job_id))
        deleted, _ = await self.mutate('delete', self.asset['revision'])
        self.assertEqual(await self.evidence(), self.before)
        # 到达凭据绑定就表示越过素材门槛，必须在此之前拒绝，绝不构造外部请求。
        with patch.object(ProviderJobBindingService, 'require', AsyncMock(side_effect=AssertionError('不应进入供应商绑定'))) as binding:
            for _ in range(2):
                async with self.sessions() as db:
                    with self.assertRaises(ServiceWarning) as raised:
                        await ProviderSubmitIntentService.begin(db, self.lease, 'a' * 64)
                    self.assertEqual(raised.exception.data['errorCode'], 'REFERENCE_UNAVAILABLE')
                    self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 0)
                    self.assertEqual(await db.scalar(text('SELECT orchestration_state FROM hf_creation_job')), '1')
            binding.assert_not_awaited()
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await ReferenceCompileService.resolve(db, self.owner, int(self.project_id), self.input, {'reference_image': ('image',)})
        await self.mutate('restore', deleted['data']['revision'])
        self.assertEqual(await self.evidence(), self.before)
        async with self.sessions() as db:
            await GenerationAccessService.require(db, await db.get(HfCreationJob, self.job_id))
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 0)
