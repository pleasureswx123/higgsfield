"""模拟密钥验证输入边界，测试不连接外部供应商或数据库。"""

import unittest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from common.router import APIRouterPro
from config.database import _engine_options
from config.env import DataBaseConfig
from module_higgsfield.controller.credential_route import CredentialRoute
from module_higgsfield.entity.vo.credential_vo import CredentialCreate


SECRET = 'test-only-secret-DO-NOT-ECHO'


def valid_body():
    return dict(
        accountId='1',
        ownerId='2',
        name='测试凭据',
        connectionVersionId='3',
        apiKey=SECRET,
        validFrom='2026-10-27T08:00:00+08:00',
        validUntil='2027-10-27T08:00:00+08:00',
    )


class CredentialBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI()
        router = APIRouterPro(route_class=CredentialRoute)

        @router.post('/credentials')
        async def create(body: CredentialCreate):
            return body.model_dump(mode='json', by_alias=True)

        self.app.include_router(router)
        self.client = AsyncClient(transport=ASGITransport(app=self.app), base_url='http://test')

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_success_excludes_secret_and_normalizes_time(self):
        result = await self.client.post('/credentials', json=valid_body())
        self.assertEqual(result.status_code, 200)
        self.assertNotIn(SECRET, result.text)
        self.assertNotIn('apiKey', result.json())
        self.assertEqual(result.json()['validFrom'], '2026-10-27T00:00:00Z')
        value = CredentialCreate.model_validate(valid_body())
        self.assertNotIn(SECRET, repr(value))
        self.assertEqual(value.api_key.get_secret_value(), SECRET)

    async def test_invalid_inputs_never_echo_body_or_field_names(self):
        changes = [
            {'apiKey': SECRET + '\n'},
            {'apiKey': {'nested': SECRET}},
            {SECRET: SECRET},
            {'accountId': SECRET},
            {'validFrom': SECRET},
            {'validUntil': '2026-10-26T00:00:00Z'},
            {'validFrom': '2026-10-27T08:00:00'},
        ]
        for change in changes:
            with self.subTest(change=list(change)):
                result = await self.client.post('/credentials', json=valid_body() | change)
                self.assertEqual(result.status_code, 422)
                self.assertNotIn(SECRET, result.text)
                self.assertEqual(result.json()['errorCode'], 'CREDENTIAL_INPUT_INVALID')
        result = await self.client.post(
            '/credentials',
            content='{"apiKey":"' + SECRET,
            headers={'Content-Type': 'application/json'},
        )
        self.assertEqual(result.status_code, 422)
        self.assertNotIn(SECRET, result.text)

    def test_model_exception_and_sql_options_hide_inputs(self):
        with self.assertRaises(ValidationError) as error:
            CredentialCreate.model_validate(valid_body() | {'accountId': SECRET})
        self.assertNotIn(SECRET, str(error.exception))
        # 与实际引擎使用同一配置归一化入口，避免测试虚构连接配置。
        from config.database import _database_source

        self.assertTrue(_engine_options(_database_source(DataBaseConfig))['hide_parameters'])
