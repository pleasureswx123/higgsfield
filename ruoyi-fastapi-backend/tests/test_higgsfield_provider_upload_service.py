"""上传意图、加密响应、复用和未知防重传的真实数据库事务。"""

import asyncio
import importlib.util
import json
import os
import unittest
from unittest.mock import patch

from sqlalchemy import text

from exceptions.exception import ServiceWarning
from module_higgsfield.service.job_lease_service import JobLeaseService
from module_higgsfield.service.provider_http_service import ProviderHttpResult
from module_higgsfield.service.provider_upload_crypto_service import ProviderUploadCryptoService
from module_higgsfield.service.provider_upload_service import ProviderUploadService, UploadPreparation
from tests import test_higgsfield_provider_submit_intent as intent


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ProviderUploadServiceTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = intent.SubmitIntentTests.cleanup_schema
    migrate = intent.SubmitIntentTests.migrate
    job = intent.SubmitIntentTests.job

    async def asyncSetUp(self) -> None:
        await intent.SubmitIntentTests.asyncSetUp(self)
        for name in ('20261027_06_assets.py', '20261027_36_provider_uploads.py'):
            spec = importlib.util.spec_from_file_location('upload_service_setup', intent.pipeline.MIGRATIONS / name)
            self.migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.migration)
            await self.migrate('upgrade')
        self.upload_crypto = ProviderUploadCryptoService(self.crypto.keyring)
        async with self.sessions() as db:
            file_id = await db.scalar(
                text(
                    'INSERT INTO hf_stored_file(storage_key,sha256,byte_size,mime_type,state,create_time,update_time) '
                    "VALUES('test/file',:sha,10,'image/png','1',NOW(),NOW()) RETURNING file_id"
                ),
                {'sha': 'a' * 64},
            )
            self.asset_version_id = await db.scalar(
                text(
                    'INSERT INTO hf_asset_version(asset_id,version_no,file_id,create_user_id,create_time,update_time) '
                    'VALUES(1,1,:file,1,NOW(),NOW()) RETURNING version_id'
                ),
                {'file': file_id},
            )
            media = [
                {
                    'assetVersionId': str(self.asset_version_id),
                    'fileId': str(file_id),
                    'sha256': 'a' * 64,
                    'byteSize': '10',
                    'mimeType': 'image/png',
                    'mediaType': 'image',
                }
            ]
            await db.execute(
                text(
                    "UPDATE hf_creation_job SET input_snapshot=jsonb_set(input_snapshot,'{compiled,media}',CAST(:media AS jsonb))"
                ),
                {'media': json.dumps(media)},
            )
            await db.commit()

    async def begin(self) -> UploadPreparation:
        async with self.sessions() as db:
            return await ProviderUploadService.begin(
                db, self.lease, self.asset_version_id, required_seconds=60, crypto=self.upload_crypto
            )

    def response(self) -> ProviderHttpResult:
        return ProviderHttpResult(
            'response',
            200,
            {
                'success': True,
                'url': 'https://example.com/file?key=secret',
                'size': 10,
                'content_type': 'image/png',
                'asset_type': 'image',
                'file_name': 'file.png',
                'expires_in': 3600,
            },
        )

    async def test_concurrent_preparation_then_ready_reuse(self) -> None:
        results = await asyncio.gather(self.begin(), self.begin())
        self.assertEqual(sorted(row.status for row in results), ['busy', 'upload'])
        pending = next(row for row in results if row.status == 'upload')
        async with self.sessions() as db:
            await ProviderUploadService.record(
                db, self.lease, pending.upload_id, self.response(), crypto=self.upload_crypto
            )
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 1)
            self.assertNotIn('secret', str(await db.scalar(text('SELECT response_metadata FROM hf_provider_call'))))
        reused = await self.begin()
        self.assertEqual(reused.status, 'ready')
        self.assertEqual(reused.url.get_secret_value(), 'https://example.com/file?key=secret')
        self.assertIsNone(reused.call_id)

    async def test_crypto_failure_rolls_back_then_timeout_blocks_resend(self) -> None:
        pending = await self.begin()
        async with self.sessions() as db:
            with (
                patch.object(self.upload_crypto, 'encrypt', side_effect=RuntimeError('加密失败')),
                self.assertRaises(RuntimeError),
            ):
                await ProviderUploadService.record(
                    db, self.lease, pending.upload_id, self.response(), crypto=self.upload_crypto
                )
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_provider_upload')), '0')
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_provider_call')), '1')
            await db.rollback()
            await ProviderUploadService.record(db, self.lease, pending.upload_id, ProviderHttpResult('timeout'))
        retried = await self.begin()
        self.assertEqual(retried.status, 'unknown')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 1)
            self.assertEqual(await db.scalar(text('SELECT reserved_amount FROM hf_budget_period')), 6)

    async def test_new_lease_marks_interrupted_upload_unknown(self) -> None:
        pending = await self.begin()
        old_lease = self.lease
        async with self.sessions() as db:
            await JobLeaseService.release(db, self.lease, retry_after_seconds=0)
            self.lease = (await JobLeaseService.claim(db, 'upload-recovery'))[0]
        recovered = await self.begin()
        self.assertEqual(recovered.status, 'unknown')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_provider_call')), '3')
            with self.assertRaises(ServiceWarning):
                await ProviderUploadService.record(
                    db, old_lease, pending.upload_id, self.response(), crypto=self.upload_crypto
                )
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 1)
