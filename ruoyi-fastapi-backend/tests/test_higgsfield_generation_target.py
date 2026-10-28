"""生成目标契约、实时权限投影与历史签名兼容性。"""

import os
import unittest
from types import SimpleNamespace
from pydantic import ValidationError
from sqlalchemy import text
from exceptions.exception import PermissionException, ServiceWarning
from module_higgsfield.entity.vo.generation_input_vo import GenerationInput
from module_higgsfield.service.estimate_token_service import EstimateTokenService
from module_higgsfield.service.generation_target_service import GenerationTargetService
from module_higgsfield.service.write_service import WriteService
from tests.test_higgsfield_element_service import ElementServiceTests


class GenerationTargetContractTests(unittest.TestCase):
    def test_optional_target_preserves_old_signature_and_changes_signed_identity(self):
        source = dict(projectId='1', kind='image', modelVersionId='2', prompt={'content': []}, parameters={}, references=[])
        plain = GenerationInput(**source)
        legacy = plain.model_dump(by_alias=True, exclude={'estimate_token'})
        self.assertNotIn('targetElementId', legacy)
        self.assertEqual(EstimateTokenService.request_hash(plain), WriteService.digest(legacy))
        target = GenerationInput(**source, targetElementId='9007199254740993')
        self.assertEqual(target.model_dump(by_alias=True)['targetElementId'], '9007199254740993')
        self.assertNotEqual(EstimateTokenService.request_hash(target), EstimateTokenService.request_hash(plain))
        with self.assertRaises(ValidationError):
            GenerationInput(**{**source, 'kind': 'video'}, targetElementId='1')
        with self.assertRaises(ValidationError):
            GenerationInput(**source, targetElementId=1)


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class GenerationTargetTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = ElementServiceTests.cleanup_schema
    create = ElementServiceTests.create
    make_element = ElementServiceTests.make_element
    asyncSetUp = ElementServiceTests.asyncSetUp

    async def test_live_projection_rejects_cross_project_deleted_and_revoked_target(self):
        created = await self.make_element()
        identity = created['element']['id']
        project_id = int(self.project_id)
        job = SimpleNamespace(project_id=project_id, input_snapshot={'targetElementId': identity})
        async with self.sessions() as db:
            result = await GenerationTargetService.validate(db, self.owner, project_id, identity)
            self.assertEqual(result, {'id': identity, 'projectId': self.project_id, 'name': '主角'})
            self.assertEqual(await GenerationTargetService.project(db, self.owner, job), result)
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await GenerationTargetService.validate(db, self.owner, project_id + 999, identity)
        async with self.sessions() as db:
            await db.execute(text("DELETE FROM hf_project_role_permission WHERE permission_code='element:edit'"))
            await db.commit()
        async with self.sessions() as db:
            self.assertIsNone(await GenerationTargetService.project(db, self.owner, job))
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_element SET del_flag='2' WHERE element_id=:id"), {'id': int(identity)})
            await db.commit()
        async with self.sessions() as db:
            self.assertIsNone(await GenerationTargetService.project(db, self.owner, job))
            job.input_snapshot = {}
            self.assertIsNone(await GenerationTargetService.project(db, self.owner, job))
