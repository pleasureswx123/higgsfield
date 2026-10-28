"""真实PG迁移和本地显式测试存储；不冒充公司NAS验收。"""

import hashlib
import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from PIL import Image
from sqlalchemy import text

from exceptions.exception import PermissionException, ServiceWarning
from module_higgsfield.entity.vo.asset_vo import (
    AssetCreate,
    AssetVersionCreate,
    LibraryMove,
    LibraryQuery,
    UploadComplete,
    UploadCreate,
)
from module_higgsfield.entity.vo.folder_vo import FolderCreate
from module_higgsfield.service.folder_service import FolderService
from module_higgsfield.service.asset_service import AssetService
from module_higgsfield.service.storage_service import StoragePolicy, StorageService
from module_higgsfield.service.upload_service import UploadService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from tests import test_higgsfield_projects as projects


def png_bytes():
    buffer = io.BytesIO()
    Image.new('RGB', (16, 16), '#c0ff00').save(buffer, format='PNG')
    return buffer.getvalue()


class StorageTests(unittest.TestCase):
    def test_roundtrip_and_nas_does_not_accept_local_sentinel(self):
        with tempfile.TemporaryDirectory() as directory:
            data = png_bytes()
            storage = StorageService(StoragePolicy(directory, 'local-test', '', 4096, 1024))
            key, digest = storage.put_part(data)
            result = storage.assemble(
                [{'storage_key': key, 'sha256': digest, 'byte_size': len(data)}], len(data), digest, 'image/png'
            )
            self.assertEqual(result['width'], 16)
            with storage.open_key(result['storage_key']) as file:
                self.assertEqual(file.read(), data)
            with self.assertRaises(ValueError):
                with storage.open_key('../outside'):
                    pass
            Path(directory, '.nas-ready').write_text('yes')
            nas = StorageService(StoragePolicy(directory, 'nas', '//company/share', 4096, 1024))
            with self.assertRaises(ServiceWarning):
                nas.verify_root()


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用独立 schema 数据库测试')
class AssetDatabaseTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = projects.ProjectDatabaseTests.cleanup_schema
    create = projects.ProjectDatabaseTests.create

    async def asyncSetUp(self):
        await projects.ProjectDatabaseTests.asyncSetUp(self)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.storage = StorageService(StoragePolicy(self.directory.name, 'local-test', '', 4096, 1024, part_size=64))
        async with self.engine.begin() as conn:
            for filename in ('20261027_04_folders.py', '20261027_06_assets.py'):
                path = Path(__file__).resolve().parents[1] / 'alembic/versions' / filename
                spec = importlib.util.spec_from_file_location(filename[:-3], path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                def migrate(sync_conn):
                    with Operations.context(MigrationContext.configure(sync_conn)):
                        module.upgrade()

                await conn.run_sync(migrate)
            for permission in ('asset:read', 'asset:reference', 'asset:upload', 'asset:create', 'asset:edit', 'folder:write'):
                await conn.execute(
                    text("""INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope)
                    SELECT role_id,:permission,'project' FROM hf_project_role WHERE code='owner'
                    ON CONFLICT DO NOTHING"""),
                    {'permission': permission},
                )
        result, _ = await self.create()
        self.project_id = result['data']['id']

    async def new_upload(self, data=None):
        data = data or png_bytes()
        async with self.sessions() as db:
            result, _ = await UploadService.create(
                db,
                self.owner,
                UploadCreate(
                    projectId=self.project_id, fileName='测试.png', byteSize=str(len(data)), mimeType='image/png'
                ),
                str(uuid4()),
                self.storage,
            )
        return int(result['data']['id']), data

    async def send_part(self, upload_id, data, number=1, total=None):
        async def stream():
            yield data

        total = total or len(data)
        offset = (number - 1) * self.storage.policy.part_size
        async with self.sessions() as db:
            return await UploadService.put_part(
                db,
                self.owner,
                upload_id,
                number,
                f'bytes {offset}-{offset + len(data) - 1}/{total}',
                hashlib.sha256(data).hexdigest(),
                stream(),
                self.storage,
            )

    async def ready_upload(self):
        upload_id, data = await self.new_upload()
        for offset in range(0, len(data), 64):
            await self.send_part(upload_id, data[offset : offset + 64], offset // 64 + 1, len(data))
        async with self.sessions() as db:
            result, _ = await UploadService.complete(
                db,
                self.owner,
                upload_id,
                UploadComplete(sha256=hashlib.sha256(data).hexdigest()),
                str(uuid4()),
                self.storage,
            )
            self.assertEqual(result['data']['state'], 'ready')
        return upload_id

    async def test_upload_bind_replay_and_immutable_versions(self):
        upload_id = await self.ready_upload()
        payload = AssetCreate(projectId=self.project_id, uploadId=str(upload_id), name='素材')
        key = str(uuid4())
        async with self.sessions() as db:
            result, _ = await AssetService.bind(db, self.owner, payload, key)
            asset = result['data']
        async with self.sessions() as db:
            replay, replayed = await AssetService.bind(db, self.owner, payload, key)
            self.assertTrue(replayed)
            self.assertEqual(result, replay)
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await AssetService.bind(db, self.owner, payload, str(uuid4()))
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await UploadService.cancel(db, self.owner, upload_id)
        next_upload = await self.ready_upload()
        async with self.sessions() as db:
            version, _ = await AssetService.bind(
                db,
                self.owner,
                AssetVersionCreate(revision=asset['revision'], uploadId=str(next_upload)),
                str(uuid4()),
                asset_id=int(asset['id']),
            )
            self.assertEqual(version['data']['versionNo'], 2)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_asset_version')), 2)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_stored_file')), 2)

    async def test_private_upload_and_part_conflict(self):
        upload_id, data = await self.new_upload()
        first = await self.send_part(upload_id, data[:64], 1, len(data))
        repeated = await self.send_part(upload_id, data[:64], 1, len(data))
        self.assertEqual(first, repeated)
        with self.assertRaises(ServiceWarning):
            await self.send_part(upload_id, b'x' * 64, 1, len(data))
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await UploadService.get(db, self.other, upload_id)
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await UploadService.complete(
                    db,
                    self.owner,
                    upload_id,
                    UploadComplete(sha256=hashlib.sha256(data).hexdigest()),
                    str(uuid4()),
                    self.storage,
                )

    async def test_own_scope_requires_actual_object_owner(self):
        async with self.sessions() as db:
            await db.execute(
                text("UPDATE hf_project_role_permission SET data_scope='own' WHERE permission_code='asset:edit'")
            )
            await db.commit()
        async with self.sessions() as db:
            await WorkspaceService.authorize(db, self.owner, int(self.project_id), 'asset:edit', owner_id=1)
        async with self.sessions() as db:
            with self.assertRaises(PermissionException):
                await WorkspaceService.authorize(db, self.owner, int(self.project_id), 'asset:edit', owner_id=2)
        async with self.sessions() as db:
            with self.assertRaises(PermissionException):
                await WorkspaceService.authorize(db, self.owner, int(self.project_id), 'asset:edit')

    async def test_wrong_hash_preserves_fixed_completion_identity(self):
        upload_id, data = await self.new_upload()
        for offset in range(0, len(data), 64):
            await self.send_part(upload_id, data[offset : offset + 64], offset // 64 + 1, len(data))
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await UploadService.complete(
                    db, self.owner, upload_id, UploadComplete(sha256='0' * 64), str(uuid4()), self.storage
                )
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await UploadService.complete(
                    db,
                    self.owner,
                    upload_id,
                    UploadComplete(sha256=hashlib.sha256(data).hexdigest()),
                    str(uuid4()),
                    self.storage,
                )
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_stored_file')), 0)

    async def test_preview_range_copy_provenance_and_delete_relocation(self):
        upload_id = await self.ready_upload()
        async with self.sessions() as db:
            folder, _ = await FolderService.mutate(
                db,
                self.owner,
                'create',
                FolderCreate(name='媒体目录').model_dump(by_alias=True),
                str(uuid4()),
                project_id=int(self.project_id),
            )
        folder = folder['data']
        async with self.sessions() as db:
            response, _ = await AssetService.bind(
                db,
                self.owner,
                AssetCreate(projectId=self.project_id, uploadId=str(upload_id), name='测试素材', folderId=folder['id']),
                str(uuid4()),
            )
        asset = response['data']
        async with self.sessions() as db:
            stream, headers, mime, status = await AssetService.media(
                db, self.owner, int(asset['currentVersionId']), 'bytes=0-7', storage=self.storage
            )
            self.assertEqual(b''.join([chunk async for chunk in stream]), png_bytes()[:8])
            self.assertEqual(status, 206)
            self.assertEqual(headers['Content-Length'], '8')
            self.assertEqual(mime, 'image/png')
        async with self.sessions() as db:
            with self.assertRaises(PermissionException):
                await AssetService.media(
                    db, self.owner, int(asset['currentVersionId']), download=True, storage=self.storage
                )
        async with self.sessions() as db:
            copied, _ = await FolderService.mutate(
                db,
                self.owner,
                'copy',
                {'revision': folder['revision'], 'targetParentId': None},
                str(uuid4()),
                folder_id=int(folder['id']),
            )
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_stored_file')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_asset')), 2)
            self.assertEqual(
                await db.scalar(
                    text('SELECT count(*) FROM hf_asset_version WHERE source_asset_version_id IS NOT NULL')
                ),
                1,
            )
        async with self.sessions() as db:
            await FolderService.mutate(
                db, self.owner, 'delete', {'revision': folder['revision']}, str(uuid4()), folder_id=int(folder['id'])
            )
            listing = await AssetService.library(db, self.owner, int(self.project_id), LibraryQuery())
            self.assertEqual(listing.rows[0]['asset']['id'], asset['id'])
            entry = listing.rows[0]
        async with self.sessions() as db:
            result, _ = await AssetService.move(
                db,
                self.owner,
                int(self.project_id),
                LibraryMove(entryId=entry['entryId'], revision=entry['revision'], folderId=copied['data']['id']),
                str(uuid4()),
            )
            self.assertEqual(result['data']['folderId'], copied['data']['id'])
