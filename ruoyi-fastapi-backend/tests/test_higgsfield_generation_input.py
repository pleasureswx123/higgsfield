"""正式输入准备覆盖草稿一致性、规格歧义和发布授权边界。"""

import json
import os
import unittest
from types import SimpleNamespace
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import text

from exceptions.exception import ServiceWarning
from module_admin.entity.vo.user_vo import CurrentUserModel
from module_higgsfield.entity.vo.draft_vo import DraftCreate
from module_higgsfield.entity.vo.generation_input_vo import GenerationInput
from module_higgsfield.service.draft_service import DraftService
from module_higgsfield.service.generation_input_service import GenerationInputService
from tests.test_higgsfield_model_capabilities import capability
from tests.test_higgsfield_model_catalog import CatalogTests


class GenerationInputContractTests(unittest.TestCase):
    def test_forbidden_client_fields_and_draft_pair(self) -> None:
        body = {
            'projectId': '1',
            'kind': 'image',
            'modelVersionId': '2',
            'prompt': {'content': []},
            'parameters': {},
            'references': [],
        }
        self.assertEqual(GenerationInput(**body).references, [])
        for extra in (
            {'credentialVersionId': '9'},
            {'modelVariantId': '9'},
            {'amount': '0'},
            {'draftId': '1'},
            {'draftRevision': '1'},
        ):
            with self.assertRaises(ValidationError):
                GenerationInput(**body, **extra)
        cap = capability()
        with self.assertRaises(ServiceWarning):
            GenerationInputService.select_variant(cap, {}, [])
        with self.assertRaises(ServiceWarning):
            GenerationInputService.select_variant(
                cap, {}, [SimpleNamespace(dimensions={}), SimpleNamespace(dimensions={})]
            )


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class GenerationInputTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = CatalogTests.cleanup_schema

    async def asyncSetUp(self) -> None:
        await CatalogTests.asyncSetUp(self)
        cap = capability().model_dump(by_alias=True)
        cap['referenceRules'] = {'maxTotal': 0, 'roles': {}}
        cap['variantDimensions'] = {'resolution': {'type': 'string', 'enum': ['720p', '1080p']}}
        async with self.sessions() as db:
            await db.execute(
                text('UPDATE hf_model_profile_version SET capabilities=CAST(:cap AS jsonb)'), {'cap': json.dumps(cap)}
            )
            self.variant_id = await db.scalar(
                text(
                    'INSERT INTO hf_model_variant(model_version_id,variant_key,dimensions,create_time,update_time) VALUES(:v,\'test\',\'{"resolution":"720p"}\',NOW(),NOW()) RETURNING variant_id'
                ),
                {'v': int(self.model_version_id)},
            )
            await db.commit()

    def payload(self, **changes) -> GenerationInput:
        values = {
            'projectId': str(self.project_id),
            'kind': 'image',
            'modelVersionId': self.model_version_id,
            'prompt': {'content': []},
            'parameters': {'duration': 6},
            'references': [],
        }
        values.update(changes)
        return GenerationInput(**values)

    async def prepare(self, payload: GenerationInput | None = None, user: CurrentUserModel | None = None) -> dict:
        async with self.sessions() as db:
            db.autoflush = False
            return await GenerationInputService.prepare(db, user or self.owner, payload or self.payload())

    async def test_normalization_variant_and_live_authorization(self) -> None:
        result = await self.prepare()
        self.assertEqual(result['modelVariantId'], str(self.variant_id))
        self.assertEqual(result['inputSnapshot']['parameters']['resolution'], '720p')
        self.assertEqual(result['inputSnapshot']['compiled']['media'], [])
        with self.assertRaises(ServiceWarning):
            await self.prepare(user=self.other)
        with self.assertRaises(ServiceWarning):
            await self.prepare(self.payload(parameters={}))
        with self.assertRaises(ServiceWarning):
            await self.prepare(self.payload(parameters={'resolution': '1080p', 'duration': 4}))
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_model_profile_version SET status='3'"))
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.prepare()

    async def test_saved_draft_must_match_revision_and_content(self) -> None:
        payload = self.payload()
        async with self.sessions() as db:
            saved, _ = await DraftService.save(
                db,
                self.owner,
                DraftCreate(
                    projectId=payload.project_id,
                    kind=payload.kind,
                    body={
                        'prompt': payload.prompt,
                        'parameters': payload.parameters,
                        'modelVersionId': payload.model_version_id,
                    },
                ),
                str(uuid4()),
            )
        draft_id = saved['data']['id']
        result = await self.prepare(self.payload(draftId=draft_id, draftRevision='1'))
        self.assertEqual(result['inputSnapshot']['draftId'], draft_id)
        with self.assertRaises(ServiceWarning):
            await self.prepare(self.payload(draftId=draft_id, draftRevision='2'))
        with self.assertRaises(ServiceWarning):
            await self.prepare(self.payload(draftId=draft_id, draftRevision='1', parameters={'duration': 8}))
