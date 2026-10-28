"""真实HTTP路由与隔离数据库串联，登录身份注入不代表真实JWT验收。"""
import os
import unittest
from uuid import uuid4
import httpx
from fastapi import FastAPI
from sqlalchemy import text
from common.aspect.db_session import get_db_session_provider
from exceptions.handle import handle_exception
from module_admin.service.login_service import LoginService
from module_higgsfield.controller.element_import_controller import element_import_controller as router
from tests import test_higgsfield_element_import_confirm as fixtures


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ElementImportHttpDatabaseTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = fixtures.ElementImportConfirmTests.cleanup_schema
    create = fixtures.ElementImportConfirmTests.create
    migrate = fixtures.ElementImportConfirmTests.migrate
    send_part = fixtures.ElementImportConfirmTests.send_part
    upload = fixtures.ElementImportConfirmTests.upload
    accept = fixtures.ElementImportConfirmTests.accept

    async def asyncSetUp(self):
        await fixtures.ElementImportConfirmTests.asyncSetUp(self)
        self.app = FastAPI()
        handle_exception(self.app)
        self.app.include_router(router)

        async def database():
            async with self.sessions() as db:
                yield db

        async def actor():
            return self.owner

        self.app.dependency_overrides[get_db_session_provider(None)] = database
        for dependency in router.dependencies:
            self.app.dependency_overrides[dependency.dependency] = actor
        self.app.dependency_overrides[LoginService.get_current_user] = actor
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test')
        self.addAsyncCleanup(self.client.aclose)

    async def test_http_edit_conflict_confirmation_replay_and_revocation(self):
        path = f'/api/v1/imports/elements/{self.identity}'
        summary = (await self.client.get(path)).json()
        self.assertEqual(summary['data']['revision'], '2')
        page = (await self.client.get(path + '/rows')).json()
        self.assertEqual(page['total'], 2)
        row = page['rows'][1]
        edit = await self.client.patch(path + '/rows/2', json={
            'revision': row['revision'], 'candidate': row['candidate'], 'isSelected': False},
            headers={'Idempotency-Key': str(uuid4())})
        self.assertEqual(edit.json()['code'], 200)
        self.assertEqual(edit.json()['data']['batchRevision'], '3')
        stale = await self.client.post(path + '/confirm', json={'revision': '2'},
                                       headers={'Idempotency-Key': str(uuid4())})
        self.assertNotEqual(stale.json()['code'], 200)
        self.assertEqual(stale.json()['data']['errorCode'], 'REVISION_CONFLICT')
        headers = {'Idempotency-Key': str(uuid4())}
        first = await self.client.post(path + '/confirm', json={'revision': '3'}, headers=headers)
        self.assertEqual(first.json()['data']['createdCount'], 1)
        repeated = await self.client.post(path + '/confirm', json={'revision': '3'}, headers=headers)
        self.assertEqual(first.json(), repeated.json())
        self.assertEqual(repeated.headers['Idempotent-Replayed'], 'true')
        finished = (await self.client.get(path)).json()['data']
        self.assertEqual(finished['status'], 'finished')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_element')), 1)
            await db.execute(text("DELETE FROM hf_project_role_permission WHERE permission_code='element:import'"))
            await db.commit()
        revoked = await self.client.post(path + '/confirm', json={'revision': '3'}, headers=headers)
        self.assertEqual(revoked.json()['code'], 403)
        self.assertNotIn('Idempotent-Replayed', revoked.headers)

    async def test_creation_permission_revocation_preserves_review_but_prevents_confirmation(self):
        path = f'/api/v1/imports/elements/{self.identity}'
        async with self.sessions() as db:
            await db.execute(text("DELETE FROM hf_project_role_permission WHERE permission_code='element:create'"))
            await db.commit()
        page = (await self.client.get(path + '/rows')).json()
        self.assertEqual(page['code'], 200)
        self.assertEqual(page['total'], 2)
        headers = {'Idempotency-Key': str(uuid4())}
        denied = await self.client.post(path + '/confirm', json={'revision': '2'}, headers=headers)
        self.assertEqual(denied.json()['code'], 403)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_element')), 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_element_revision')), 0)
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM hf_import_row WHERE element_id IS NOT NULL")), 0)
            await db.execute(text("INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope) SELECT role_id,'element:create','project' FROM hf_project_role WHERE code='owner'"))
            await db.commit()
        accepted = await self.client.post(path + '/confirm', json={'revision': '2'}, headers=headers)
        self.assertEqual(accepted.json()['code'], 200)
        self.assertEqual(accepted.json()['data']['createdCount'], 2)
        replay = await self.client.post(path + '/confirm', json={'revision': '2'}, headers=headers)
        self.assertEqual(replay.headers['Idempotent-Replayed'], 'true')
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_element')), 2)
