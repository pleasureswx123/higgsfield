"""真实迁移与短事务验证：去重领取、过期栅栏、不可变登记、退避与错误白名单。"""
import asyncio
import importlib.util
import os
from pathlib import Path
import unittest
import hashlib
import io
import tempfile
from unittest.mock import patch
from PIL import Image
from sqlalchemy import text
from exceptions.exception import ServiceWarning
from module_higgsfield.service.media_derivative_service import MediaDerivativeService as Service
from module_higgsfield.service.image_thumbnail_worker import ImageThumbnailWorker
from module_higgsfield.service.storage_service import StoragePolicy, StorageService
from module_higgsfield.service.output_read_service import OutputReadService
from module_higgsfield.service.asset_service import AssetService
from tests import test_higgsfield_output_read as fixture


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class MediaDerivativeTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = fixture.OutputReadTests.cleanup_schema
    migrate = fixture.OutputReadTests.migrate
    job = fixture.OutputReadTests.job
    output = fixture.OutputReadTests.output
    create = fixture.OutputReadTests.create

    async def asyncSetUp(self):
        await fixture.OutputReadTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location('derivative_migration',
            Path(__file__).resolve().parents[1] / 'alembic/versions/20261028_76_media_derivatives.py')
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')

    async def enqueue(self):
        async with self.sessions() as db:
            return await Service.enqueue(db, self.file_id)

    async def claim(self, worker='thumb-one'):
        async with self.sessions() as db:
            return await Service.claim(db, worker)

    def facts(self):
        return {'storage_key': 'media/' + 'c' * 32, 'sha256': 'd' * 64,
                'byte_size': 256, 'mime_type': 'image/webp', 'width': 128, 'height': 64, 'seconds': None}

    async def test_duplicate_queue_claim_and_immutable_completion(self):
        identities = await asyncio.gather(self.enqueue(), self.enqueue())
        self.assertEqual(identities[0], identities[1])
        claims = await asyncio.gather(self.claim(), self.claim())
        self.assertEqual(sum(value is not None for value in claims), 1)
        claim = next(value for value in claims if value)
        async with self.sessions() as db:
            derived = await Service.complete(db, claim['id'], 'thumb-one', claim['revision'], self.facts())
            self.assertEqual(await Service.complete(db, claim['id'], 'thumb-one', claim['revision'], self.facts()), derived)
            with self.assertRaises(ServiceWarning) as failure:
                await Service.complete(db, claim['id'], 'thumb-one', claim['revision'], self.facts() | {'width': 64})
            self.assertEqual(failure.exception.data['errorCode'], 'THUMBNAIL_IMMUTABLE')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_stored_file')), 2)
            self.assertEqual(await db.scalar(text('SELECT source_file_id FROM hf_media_derivative')), self.file_id)
            self.assertEqual(await db.scalar(text('SELECT derived_file_id FROM hf_media_derivative')), derived)
            comments = (await db.execute(text("SELECT count(*) FROM pg_attribute WHERE attrelid='hf_media_derivative'::regclass AND attnum>0 AND NOT attisdropped AND col_description(attrelid,attnum) IS NULL"))).scalar_one()
            self.assertEqual(comments, 0)
        self.assertIsNone(await self.claim())

    async def test_expired_worker_cannot_register_and_failure_backoff_is_bounded(self):
        identity = await self.enqueue()
        old = await self.claim()
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_media_derivative SET lease_until=clock_timestamp()-interval '1 second'"))
            await db.commit()
        new = await self.claim('thumb-two')
        self.assertGreater(new['revision'], old['revision'])
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning) as failure:
                await Service.complete(db, identity, 'thumb-one', old['revision'], self.facts())
            self.assertEqual(failure.exception.data['errorCode'], 'THUMBNAIL_LEASE_LOST')
            await Service.failure(db, identity, 'thumb-two', new['revision'], 'private-secret-path')
            self.assertEqual(await db.scalar(text('SELECT error_code FROM hf_media_derivative')), 'THUMBNAIL_PROCESSING_FAILED')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_stored_file')), 1)
            delay = await db.scalar(text('SELECT extract(epoch from next_action_time-update_time) FROM hf_media_derivative'))
            self.assertGreater(delay, 0)
            self.assertLessEqual(delay, 300)
            await db.commit()
        self.assertIsNone(await self.claim())

    async def test_unavailable_source_and_terminal_error_never_register_file(self):
        identity = await self.enqueue()
        claim = await self.claim()
        async with self.sessions() as db:
            await Service.failure(db, identity, 'thumb-one', claim['revision'], 'MEDIA_INVALID')
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_media_derivative')), '4')
            await db.commit()
        self.assertIsNone(await self.claim())
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_stored_file SET state='2'"))
            await db.commit()
            with self.assertRaises(ServiceWarning):
                await Service.enqueue(db, self.file_id)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_stored_file')), 1)

    async def real_source(self, directory):
        storage = StorageService(StoragePolicy(directory, 'local-test', '', 8 * 1024 * 1024, 4_000_000))
        with Image.new('RGB', (1200, 600), 'blue') as picture:
            buffer = io.BytesIO()
            picture.save(buffer, 'PNG')
            content = buffer.getvalue()
        key = 'media/' + 'a' * 32
        with storage.open_key(key, write=True) as handle:
            handle.write(content)
        async with self.sessions() as db:
            await db.execute(text('UPDATE hf_stored_file SET storage_key=:key,sha256=:sha,byte_size=:size,width=1200,height=600'),
                {'key': key, 'sha': hashlib.sha256(content).hexdigest(), 'size': len(content)})
            await db.execute(text("UPDATE hf_generated_output SET archive_state='2',file_id=:id"), {'id': self.file_id})
            await db.commit()
        return storage, content

    async def test_unavailable_source_waits_and_resumes_only_after_restored(self):
        await self.enqueue()
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_stored_file SET state='2' WHERE file_id=:id"), {'id': self.file_id})
            await db.commit()
        self.assertIsNone(await self.claim())
        async with self.sessions() as db:
            row = (await db.execute(text('SELECT state,error_code,attempts,lease_owner,next_action_time>clock_timestamp() AS delayed FROM hf_media_derivative'))).one()
            self.assertEqual((row.state, row.error_code, row.attempts, row.lease_owner, row.delayed),
                             ('3', 'THUMBNAIL_SOURCE_UNAVAILABLE', 0, None, True))
            await db.execute(text("UPDATE hf_media_derivative SET next_action_time=clock_timestamp()-interval '1 second'"))
            await db.commit()
        # 到期但仍隔离，继续等待，不能解码或绕过源文件状态。
        self.assertIsNone(await self.claim())
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_stored_file SET state='1' WHERE file_id=:id"), {'id': self.file_id})
            await db.execute(text("UPDATE hf_media_derivative SET next_action_time=clock_timestamp()-interval '1 second'"))
            await db.commit()
        claim = await self.claim()
        self.assertIsNotNone(claim)
        async with self.sessions() as db:
            await Service.complete(db, claim['id'], 'thumb-one', claim['revision'], self.facts())
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_media_derivative')), '2')

    async def test_source_quarantined_before_registration_remains_retryable(self):
        with tempfile.TemporaryDirectory() as directory:
            storage, _ = await self.real_source(directory)
            original = Service.complete
            async def quarantine_then_complete(db, *args, **kwargs):
                async with self.sessions() as other:
                    await other.execute(text("UPDATE hf_stored_file SET state='2' WHERE file_id=:id"), {'id': self.file_id})
                    await other.commit()
                return await original(db, *args, **kwargs)
            worker = ImageThumbnailWorker(self.sessions, 'thumb-one', storage=storage, batch_size=1)
            with patch.object(Service, 'complete', side_effect=quarantine_then_complete):
                self.assertEqual((await worker.run_once())[0]['status'], 'failed')
            self.assertEqual(len(list((Path(directory) / 'media').iterdir())), 1)
            async with self.sessions() as db:
                row = (await db.execute(text('SELECT state,error_code FROM hf_media_derivative'))).one()
                self.assertEqual(tuple(row), ('3', 'THUMBNAIL_SOURCE_UNAVAILABLE'))
                await db.execute(text("UPDATE hf_stored_file SET state='1' WHERE file_id=:id"), {'id': self.file_id})
                await db.execute(text("UPDATE hf_media_derivative SET next_action_time=clock_timestamp()-interval '1 second'"))
                await db.commit()
            self.assertEqual((await worker.run_once())[0]['status'], 'handled')

    async def test_worker_discovers_real_image_and_recovers_commit_response_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            storage, content = await self.real_source(directory)
            worker = ImageThumbnailWorker(self.sessions, 'thumb-one', storage=storage, batch_size=2)
            original = Service.complete
            async def lose_response(*args, **kwargs):
                await original(*args, **kwargs)
                raise ConnectionError('模拟提交已完成但响应丢失')
            with patch.object(Service, 'complete', side_effect=lose_response):
                results = await worker.run_once()
            self.assertEqual(sum(row['status'] == 'handled' for row in results), 1)
            async with self.sessions() as db:
                row = (await db.execute(text('SELECT f.storage_key,f.width,f.height FROM hf_media_derivative d '
                    'JOIN hf_stored_file f ON f.file_id=d.derived_file_id'))).one()
                self.assertEqual((row.width, row.height), (512, 256))
                with storage.open_key(row.storage_key) as handle:
                    with Image.open(handle) as thumbnail:
                        self.assertEqual(thumbnail.format, 'WEBP')
                self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_stored_file')), 2)
            again = await worker.run_once()
            self.assertTrue(all(row['status'] == 'skipped' for row in again))
            with storage.open_key('media/' + 'a' * 32) as handle:
                self.assertEqual(handle.read(), content)

    async def test_worker_rolls_back_failed_registration_and_cleans_only_unbound_file(self):
        with tempfile.TemporaryDirectory() as directory:
            storage, content = await self.real_source(directory)
            worker = ImageThumbnailWorker(self.sessions, 'thumb-one', storage=storage, batch_size=1)
            with patch.object(Service, 'complete', side_effect=RuntimeError('模拟登记未执行')):
                results = await worker.run_once()
            self.assertEqual(results[0]['status'], 'failed')
            self.assertEqual(len(list((Path(directory) / 'media').iterdir())), 1)
            async with self.sessions() as db:
                self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_stored_file')), 1)
                self.assertEqual(await db.scalar(text('SELECT state FROM hf_media_derivative')), '3')

    async def test_authorized_thumbnail_stream_range_head_and_revocation(self):
        with tempfile.TemporaryDirectory() as directory:
            storage, original = await self.real_source(directory)
            async with self.sessions() as db:
                with self.assertRaises(ServiceWarning) as missing:
                    await OutputReadService.media(db, self.owner, self.identity, thumbnail=True, storage=storage)
                self.assertEqual(missing.exception.data['errorCode'], 'THUMBNAIL_NOT_READY')
            worker = ImageThumbnailWorker(self.sessions, 'thumb-reader', storage=storage, batch_size=1)
            self.assertEqual((await worker.run_once())[0]['status'], 'handled')
            async with self.sessions() as db:
                stream, headers, mime, status = await OutputReadService.media(
                    db, self.owner, self.identity, thumbnail=True, storage=storage)
                self.assertFalse(db.in_transaction())
                content = b''.join([chunk async for chunk in stream])
                self.assertEqual((mime, status, headers['Cache-Control']), ('image/webp', 200, 'no-store'))
                with Image.open(io.BytesIO(content)) as picture:
                    self.assertEqual(picture.size, (512, 256))
                stream, _, _, status = await OutputReadService.media(
                    db, self.owner, self.identity, 'bytes=2-7', thumbnail=True, storage=storage)
                self.assertEqual((b''.join([chunk async for chunk in stream]), status), (content[2:8], 206))
                stream, _, _, status = await OutputReadService.media(
                    db, self.owner, self.identity, thumbnail=True, head=True, storage=storage)
                self.assertEqual((stream, status), (None, 200))
                stream, _, mime, _ = await OutputReadService.media(db, self.owner, self.identity, storage=storage)
                self.assertEqual((b''.join([chunk async for chunk in stream]), mime), (original, 'image/png'))
            for statement, expected in (
                ("UPDATE hf_stored_file SET state='2' WHERE file_id=:id", 'FILE_NOT_READY'),
                ("UPDATE hf_generated_output SET del_flag='2'", 'RESOURCE_NOT_FOUND'),
                ("UPDATE hf_project_member SET status='1'", None),
            ):
                async with self.sessions() as db:
                    await db.execute(text(statement), {'id': self.file_id})
                    with self.assertRaises(ServiceWarning) as denied:
                        await OutputReadService.media(db, self.owner, self.identity, thumbnail=True, storage=storage)
                    if expected:
                        self.assertEqual(denied.exception.data['errorCode'], expected)
                    await db.rollback()

    async def test_asset_thumbnail_uses_version_source_and_rejects_recycled_or_foreign_access(self):
        with tempfile.TemporaryDirectory() as directory:
            storage, _ = await self.real_source(directory)
            async with self.sessions() as db:
                asset_id = await db.scalar(text("INSERT INTO hf_asset(space_id,asset_name,media_type,create_user_id,create_time,update_time) "
                    "SELECT space_id,'验收缩略图','image',:owner,now(),now() FROM hf_asset_space "
                    "WHERE project_id=(SELECT project_id FROM hf_creation_job LIMIT 1) RETURNING asset_id"),
                    {'owner': self.owner.user.user_id})
                version_id = await db.scalar(text("INSERT INTO hf_asset_version(asset_id,version_no,file_id,create_user_id,create_time,update_time) "
                    "VALUES (:asset,1,:file,:owner,now(),now()) RETURNING version_id"),
                    {'asset': asset_id, 'file': self.file_id, 'owner': self.owner.user.user_id})
                await db.commit()
            await ImageThumbnailWorker(self.sessions, 'thumb-asset', storage=storage, batch_size=1).run_once()
            async with self.sessions() as db:
                stream, _, mime, _ = await AssetService.media(db, self.owner, version_id, thumbnail=True, storage=storage)
                content = b''.join([chunk async for chunk in stream])
                self.assertEqual(mime, 'image/webp')
                with Image.open(io.BytesIO(content)) as picture:
                    self.assertEqual(picture.size, (512, 256))
            async with self.sessions() as db:
                with self.assertRaises(ServiceWarning):
                    await AssetService.media(db, self.other, version_id, thumbnail=True, storage=storage)
            async with self.sessions() as db:
                await db.execute(text("UPDATE hf_asset SET del_flag='2' WHERE asset_id=:id"), {'id': asset_id})
                await db.commit()
            async with self.sessions() as db:
                with self.assertRaises(ServiceWarning) as denied:
                    await AssetService.media(db, self.owner, version_id, thumbnail=True, storage=storage)
                self.assertEqual(denied.exception.data['errorCode'], 'FILE_NOT_READY')
