"""结构化引用映射、固定版本归属与提交前授权校验。"""

import os
import unittest
from uuid import uuid4
from sqlalchemy import text
from pydantic import ValidationError
from exceptions.exception import ServiceWarning, PermissionException
from module_higgsfield.entity.vo.reference_vo import ReferenceInput
from module_higgsfield.service.reference_compile_service import ReferenceCompileService
from module_higgsfield.service.asset_service import AssetService
from module_higgsfield.entity.vo.asset_vo import AssetVersionCreate
from tests import test_higgsfield_references as references


def payload(rows):
    return ReferenceInput(
        prompt={
            'content': [
                {
                    'content': [
                        {'type': 'text', 'text': '让@普通文本保持原样'},
                        {'type': 'mention', 'referenceKey': rows[0]['referenceKey']},
                    ]
                }
            ]
        },
        references=rows,
    )


def ref(key='1', version='10', ordinal=0, **kwargs):
    return {
        'referenceKey': key,
        'assetVersionId': version,
        'mediaRole': 'reference_image',
        'ordinal': ordinal,
        **kwargs,
    }


class ReferenceCompileInputTests(unittest.TestCase):
    def test_deduplicate_preserves_mentions_and_sources(self):
        value = payload(
            [ref('1', '10', 4, elementRevisionId='20'), ref('2', '10', 0), ref('1', '11', 8, elementRevisionId='20')]
        )
        result = ReferenceCompileService.compile(value, {'10': {'fileId': '30'}, '11': {'fileId': '31'}})
        self.assertEqual([row['assetVersionId'] for row in result['media']], ['10', '11'])
        self.assertEqual(result['referenceOrdinals'], {'2': [0], '1': [0, 1]})
        self.assertEqual(result['promptParagraphs'][0][1]['ordinals'], [0, 1])
        self.assertEqual(result['promptParagraphs'][0][0]['text'], '让@普通文本保持原样')
        self.assertEqual(len(result['sources']), 3)

    def test_different_roles_remain_distinct(self):
        value = payload([ref(), ref('2', '10', 1, mediaRole='first_frame')])
        self.assertEqual(len(ReferenceCompileService.compile(value, {'10': {}})['media']), 2)

    def test_rejects_forged_keys_external_addresses_and_ambiguous_order(self):
        for rows in (
            [ref(), ref('2', '11')],
            [ref(), ref('1', '11', 1)],
            [ref(version='https://example.com/a.png')],
            [ref(ordinal=True)],
            [ref(), ref('1', '10', 1)],
        ):
            with self.subTest(rows=rows), self.assertRaises(ValidationError):
                payload(rows)
        with self.assertRaises(ValidationError):
            ReferenceInput(
                prompt={'content': [{'content': [{'type': 'mention', 'referenceKey': '999'}]}]}, references=[]
            )


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ReferenceResolveTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = references.ReferenceTests.cleanup_schema
    create = references.ReferenceTests.create
    new_upload = references.ReferenceTests.new_upload
    send_part = references.ReferenceTests.send_part
    ready_upload = references.ReferenceTests.ready_upload
    asyncSetUp = references.ReferenceTests.asyncSetUp

    def input(self, **kwargs):
        return payload(
            [
                ref(
                    version=self.asset['currentVersionId'],
                    elementRevisionId=self.source['currentRevision']['id'],
                    **kwargs,
                )
            ]
        )

    async def resolve(self, value=None, roles=None):
        async with self.sessions() as db:
            return await ReferenceCompileService.resolve(
                db,
                self.owner,
                int(self.project_id),
                value or self.input(),
                {'reference_image': ['image']} if roles is None else roles,
            )

    async def test_fixed_version_snapshot_and_model_role_intersection(self):
        compiled = await self.resolve()
        self.assertEqual(compiled['media'][0]['assetVersionId'], self.asset['currentVersionId'])
        self.assertEqual(len(compiled['media'][0]['sha256']), 64)
        self.assertNotIn('storageKey', compiled['media'][0])
        with self.assertRaises(ServiceWarning):
            await self.resolve(roles={})
        with self.assertRaises(ServiceWarning):
            await self.resolve(roles={'reference_image': ['video']})
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_asset SET del_flag='2'"))
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.resolve()

    async def test_revoked_permission_and_forged_revision_media(self):
        async with self.sessions() as db:
            await db.execute(text("DELETE FROM hf_project_role_permission WHERE permission_code='asset:reference'"))
            await db.commit()
        with self.assertRaises(PermissionException):
            await self.resolve()
        async with self.sessions() as db:
            await db.execute(
                text(
                    "INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope) SELECT role_id,'asset:reference','project' FROM hf_project_role WHERE code='owner'"
                )
            )
            await db.execute(text('DELETE FROM hf_element_revision_media'))
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.resolve()

    async def test_new_asset_version_does_not_retarget_saved_reference(self):
        upload_id = await self.ready_upload()
        async with self.sessions() as db:
            result, _ = await AssetService.bind(
                db,
                self.owner,
                AssetVersionCreate(revision=self.asset['revision'], uploadId=str(upload_id)),
                str(uuid4()),
                asset_id=int(self.asset['id']),
            )
        self.assertNotEqual(result['data']['id'], self.asset['currentVersionId'])
        compiled = await self.resolve()
        self.assertEqual(compiled['media'][0]['assetVersionId'], self.asset['currentVersionId'])
