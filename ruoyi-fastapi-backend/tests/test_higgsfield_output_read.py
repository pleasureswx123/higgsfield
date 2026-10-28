"""输出授权、敏感字段隔离与真实文件分段读取。"""

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
import unittest
from sqlalchemy import text
from exceptions.exception import ServiceWarning, PermissionException
from module_higgsfield.service.output_read_service import OutputReadService
from tests import test_higgsfield_output_archive as archive
from tests import test_higgsfield_projects as projects


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class OutputReadTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = archive.OutputArchiveTests.cleanup_schema
    migrate = archive.OutputArchiveTests.migrate
    job = archive.OutputArchiveTests.job
    output = archive.OutputArchiveTests.output
    create = projects.ProjectDatabaseTests.create

    async def asyncSetUp(self):
        await archive.OutputArchiveTests.asyncSetUp(self)
        project, _ = await self.create()
        async with self.sessions() as db:
            await db.execute(text('UPDATE hf_creation_job SET project_id=:id'), {'id': int(project['data']['id'])})
            await db.execute(
                text(
                    "INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope,create_time,update_time) SELECT role_id,'asset:read','project',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP FROM hf_project_role ON CONFLICT DO NOTHING"
                )
            )
            await db.execute(
                text('UPDATE hf_generated_output SET actual_metadata=CAST(:metadata AS jsonb)'),
                {'metadata': '{"width":128,"sourceUrl":"private"}'},
            )
            await db.commit()

    async def ready(self):
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_generated_output SET archive_state='2',file_id=:id"), {'id': self.file_id})
            await db.commit()

    async def test_pending_projection_and_download_permission(self):
        async with self.sessions() as db:
            result = await OutputReadService.get(db, self.owner, self.identity)
            self.assertNotIn('previewUrl', result)
            self.assertNotIn('sourceUrl', result['actualMetadata'])
            self.assertNotIn('encrypted-test-source', str(result))
            with self.assertRaises(ServiceWarning):
                await OutputReadService.media(db, self.owner, self.identity)
        await self.ready()
        async with self.sessions() as db:
            result = await OutputReadService.get(db, self.owner, self.identity)
            self.assertIn('previewUrl', result)
            self.assertNotIn('downloadUrl', result)
            with self.assertRaises(PermissionException):
                await OutputReadService.media(db, self.owner, self.identity, download=True)
            with self.assertRaises(ServiceWarning):
                await OutputReadService.get(db, self.other, self.identity)
            await db.execute(text("UPDATE hf_project_member SET status='1'"))
            await db.commit()
            with self.assertRaises(ServiceWarning):
                await OutputReadService.get(db, self.owner, self.identity)

    async def test_range_stream_closes_file_and_releases_transaction(self):
        await self.ready()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'media.bin'
            path.write_bytes(bytes(range(64)))
            handles = []
            async with self.sessions() as db:

                class LocalStorage:
                    @contextmanager
                    def open_key(inner, key):
                        self.assertEqual(key, 'test/archive')
                        self.assertFalse(db.in_transaction())
                        with path.open('rb') as handle:
                            handles.append(handle)
                            yield handle

                stream, headers, mime, status = await OutputReadService.media(
                    db, self.owner, self.identity, 'bytes=3-7', storage=LocalStorage()
                )
                self.assertEqual(b''.join([chunk async for chunk in stream]), bytes(range(3, 8)))
                self.assertTrue(handles[-1].closed)

                self.assertEqual(status, 206)
                self.assertEqual(mime, 'image/png')
                self.assertEqual(headers['Cache-Control'], 'no-store')
                stream, _, _, status = await OutputReadService.media(
                    db, self.owner, self.identity, head=True, storage=LocalStorage()
                )
                self.assertIsNone(stream)
                self.assertEqual(status, 200)
                self.assertTrue(handles[-1].closed)

    async def test_archive_action_requires_permission_failure_and_live_source(self):
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_generated_output SET archive_state='3'"))
            result = await OutputReadService.get(db, self.owner, self.identity)
            self.assertNotIn('output:archive', result['allowedActions'])
            await db.execute(text("INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope,create_time,update_time) SELECT role_id,'output:archive','project',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP FROM hf_project_role WHERE code='owner' ON CONFLICT DO NOTHING"))
            await db.commit()
        async with self.sessions() as db:
            result = await OutputReadService.get(db, self.owner, self.identity)
            self.assertIn('output:archive', result['allowedActions'])
            self.assertNotIn('source_url_ciphertext', result)
            await db.execute(text("UPDATE hf_generated_output SET source_expires_time=clock_timestamp()-interval '1 second'"))
            await db.commit()
        async with self.sessions() as db:
            result = await OutputReadService.get(db, self.owner, self.identity)
            self.assertNotIn('output:archive', result['allowedActions'])

    async def test_to_asset_action_requires_source_use_permission_and_ready_file(self):
        async with self.sessions() as db:
            await db.execute(text("INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope) SELECT role_id,'asset:reference','project' FROM hf_project_role WHERE code='owner' ON CONFLICT DO NOTHING"))
            await db.commit()
            self.assertNotIn('output:to-asset', (await OutputReadService.get(db, self.owner, self.identity))['allowedActions'])
        await self.ready()
        async with self.sessions() as db:
            self.assertIn('output:to-asset', (await OutputReadService.get(db, self.owner, self.identity))['allowedActions'])
            await db.execute(text("DELETE FROM hf_project_role_permission WHERE permission_code='asset:reference'"))
            await db.commit()
        async with self.sessions() as db:
            self.assertNotIn('output:to-asset', (await OutputReadService.get(db, self.owner, self.identity))['allowedActions'])
