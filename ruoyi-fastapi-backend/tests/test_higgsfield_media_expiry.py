"""隔离数据库与真实回环HTTP验证过期恢复，绝不访问收费供应商。"""
import json
import os
import unittest

from sqlalchemy import text

from module_higgsfield.entity.vo.provider_media_policy_vo import ProviderMediaPolicies
from module_higgsfield.service.videoplus_media_resolver import VideoPlusMediaResolver
from module_higgsfield.service.videoplus_submit_handler import VideoPlusSubmitHandler
from tests import test_higgsfield_videoplus_media_resolver as media_tests


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class MediaExpiryTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = media_tests.MediaResolverTests.asyncSetUp
    cleanup_schema = media_tests.MediaResolverTests.cleanup_schema
    migrate = media_tests.MediaResolverTests.migrate
    job = media_tests.MediaResolverTests.job
    write_source = media_tests.MediaResolverTests.write_source
    close_server = media_tests.MediaResolverTests.close_server
    respond = media_tests.MediaResolverTests.respond

    async def due(self):
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_creation_job SET next_action_time=clock_timestamp()-interval '1 second'"))
            await db.commit()

    async def expire_upload(self):
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_provider_upload SET create_time=clock_timestamp()-interval '2 days',expires_time=clock_timestamp()-interval '1 day',state='4'"))
            await db.commit()

    async def person(self):
        self.mode, self.asset_status = 'person', 'Processing'
        async with self.sessions() as db:
            cap = await db.scalar(text('SELECT capabilities FROM hf_model_profile_version'))
            cap['referenceRules'] = {'maxTotal': 1, 'roles': {'reference_person': {'mediaTypes': ['image'], 'maxCount': 1}}}
            snapshot = await db.scalar(text('SELECT input_snapshot FROM hf_creation_job'))
            snapshot['compiled']['media'][0]['mediaRole'] = 'reference_person'
            await db.execute(text("UPDATE hf_model_profile_version SET gateway_alias='mm-eva-sd-2.5',capabilities=CAST(:cap AS jsonb)"), {'cap': json.dumps(cap)})
            await db.execute(text('UPDATE hf_creation_job SET input_snapshot=CAST(:snapshot AS jsonb)'), {'snapshot': json.dumps(snapshot)})
            await db.commit()
        policy = ProviderMediaPolicies(modelVersions={str(self.model_version_id): {
            'roles': ['reference_person'], 'mimeLimits': {'image/png': 100000}, 'requiredSeconds': 60, 'evidenceRef': 'test-only'}})
        self.worker.handlers['prepare'] = VideoPlusSubmitHandler(credential_crypto=self.crypto,
            media_resolver=VideoPlusMediaResolver(credential_crypto=self.crypto, policies=policy, storage=self.storage))
        self.assertEqual((await self.worker.run_once())[0]['status'], 'handler_failed')
        self.assertEqual(self.errors, [])
        self.requests.clear()
        await self.due()

    def paths(self):
        return [row[0].split(' ')[1] for row in self.requests]

    async def test_expired_upload_and_signed_url_do_not_expire_active_id(self):
        await self.person()
        await self.expire_upload()
        self.asset_status = 'Active'
        self.assertEqual((await self.worker.run_once())[0]['status'], 'handled')
        self.assertEqual(self.paths(), ['/v1/mm/assets/get', '/v1/chat/completions'])
        self.assertNotIn(b'expired-download', self.requests[-1][1])
        # 已提交任务不能因再次调度返回准备阶段或重新提交付费生成。
        await self.due()
        await self.worker.run_once()
        self.assertEqual(self.paths().count('/v1/chat/completions'), 1)
        self.assertEqual(self.errors, [])

    async def test_explicit_invalid_id_refreshes_expired_upload_before_single_submit(self):
        await self.person()
        await self.expire_upload()
        self.asset_status = 'Expired'
        self.assertEqual((await self.worker.run_once())[0]['status'], 'handler_failed')
        self.assertEqual(self.paths(), ['/v1/mm/assets/get'])
        self.asset_status = 'Active'
        self.registered_identity = self.expected_person_id = 'asset-renewed'
        await self.due()
        self.assertEqual((await self.worker.run_once())[0]['status'], 'handled')
        self.assertEqual(self.paths(), ['/v1/mm/assets/get', '/v1/assets/upload', '/v1/mm/assets', '/v1/mm/assets/get', '/v1/chat/completions'])
        self.assertEqual(self.errors, [])

    async def test_repeated_explicit_invalidity_is_bounded(self):
        await self.person()
        self.asset_status = 'Deleted'
        for _ in range(3):
            await self.due()
            self.assertEqual((await self.worker.run_once())[0]['status'], 'handler_failed')
        self.assertEqual(self.paths(), ['/v1/mm/assets/get', '/v1/mm/assets', '/v1/mm/assets/get'])
        self.assertEqual(self.errors, [])

    async def test_errors_failed_audit_and_wrong_identity_never_reregister(self):
        await self.person()
        for http, patch in [(404, {}), (403, {}), (500, {}), (200, {'Status': 'Failed'}),
                            (200, {'Status': 'unknown'}), (200, {'Id': 'asset-other', 'Status': 'Expired'}),
                            (200, {'Status': 'Expired', 'base_resp': {'status_code': 1}})]:
            with self.subTest(http=http, patch=patch):
                self.asset_http_status, self.asset_response_patch = http, patch
                await self.due()
                self.assertEqual((await self.worker.run_once())[0]['status'], 'handler_failed')
        self.assertTrue(all(p == '/v1/mm/assets/get' for p in self.paths()))
        self.asset_disconnect = True
        await self.due()
        self.assertEqual((await self.worker.run_once())[0]['status'], 'handler_failed')
        self.assertTrue(all(p == '/v1/mm/assets/get' for p in self.paths()))
        self.assertEqual(self.errors, [])

    async def test_unknown_registration_is_not_repeated_even_after_upload_expiry(self):
        await self.person()
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_provider_call SET response_metadata=jsonb_set(response_metadata,'{assetRegistrations,eva}',CAST(:registration AS jsonb)) WHERE operation='upload'"),
                {'registration': json.dumps({'state': 'registering', 'callId': '2'})})
            await db.commit()
        await self.expire_upload()
        for _ in range(2):
            await self.due()
            self.assertEqual((await self.worker.run_once())[0]['status'], 'handler_failed')
        self.assertEqual(self.requests, [])

    async def test_project_libraries_are_isolated(self):
        await self.person()
        self.register_project, self.asset_status = 'nova', 'Active'
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_model_profile_version SET gateway_alias='mm-nova-sd-2.5'"))
            await db.commit()
        self.assertEqual((await self.worker.run_once())[0]['status'], 'handled')
        self.assertEqual(self.paths(), ['/v1/mm/assets', '/v1/mm/assets/get', '/v1/chat/completions'])
        self.assertEqual(self.errors, [])

    async def test_expired_ordinary_upload_is_refreshed_without_duplicate_generation(self):
        self.mode = 'revoke_after_upload'
        self.assertEqual((await self.worker.run_once())[0]['status'], 'handler_failed')
        await self.expire_upload()
        async with self.sessions() as db:
            await db.execute(text("UPDATE sys_role SET status='0'"))
            await db.commit()
        self.mode = 'success'
        await self.due()
        self.assertEqual((await self.worker.run_once())[0]['status'], 'handled')
        self.assertEqual(self.paths(), ['/v1/assets/upload', '/v1/assets/upload', '/v1/chat/completions'])
        self.assertEqual(self.errors, [])

class MediaExpiryOrderingTests(unittest.IsolatedAsyncioTestCase):
    async def test_ordinary_url_is_checked_after_all_person_queries(self):
        from contextlib import asynccontextmanager
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch
        from pydantic import SecretStr
        from module_higgsfield.service.provider_upload_service import UploadPreparation

        compiled = {'media': [
            dict(ordinal=0, assetVersionId='1', mediaRole='reference_image', mimeType='image/png', byteSize='10'),
            dict(ordinal=1, assetVersionId='2', mediaRole='reference_person', mimeType='image/png', byteSize='10'),
        ]}
        @asynccontextmanager
        async def sessions():
            yield object()
        context = SimpleNamespace(sessions=sessions, lease=object())
        resolver = object.__new__(VideoPlusMediaResolver)
        resolver.storage, resolver.crypto = object(), None
        resolver.policies = ProviderMediaPolicies(modelVersions={'1': {
            'roles': ['reference_image', 'reference_person'], 'mimeLimits': {'image/png': 100},
            'requiredSeconds': 60, 'evidenceRef': 'test-only'}})
        queried = False
        checks = []
        async def person(*args, **kwargs):
            nonlocal queried
            if not kwargs.get('register_only'):
                queried = True
            return SecretStr('asset://person')
        async def ready(*args, **kwargs):
            checks.append(queried)
            if queried:
                raise ValueError('模拟人物查询期间普通地址过期')
            return SecretStr('https://example.com/reference')
        target = 'module_higgsfield.service.videoplus_media_resolver.'
        with (
            patch(target + 'JobLeaseService.guard', AsyncMock(return_value=(SimpleNamespace(
                input_snapshot={'compiled': compiled}, model_version_id=1), None))),
            patch(target + 'ModelDao.version', AsyncMock(return_value=SimpleNamespace(gateway_alias='mm-eva-sd-2.5'))),
            patch(target + 'ProviderUploadService.begin', AsyncMock(side_effect=[
                UploadPreparation(1, 'ready'), UploadPreparation(2, 'registered')])),
            patch(target + 'ProviderUploadService.ready_url', AsyncMock(side_effect=ready)),
            patch.object(resolver, 'person_reference', AsyncMock(side_effect=person)),
            self.assertRaisesRegex(ValueError, '普通地址过期'),
        ):
            await resolver(context, compiled)
        self.assertEqual(checks, [False, True])
