"""固定引用更新检查的真实数据库权限与只读边界。"""
import os
import unittest
from uuid import uuid4
from sqlalchemy import text
from module_higgsfield.entity.vo.reference_vo import ReferenceUpdatesQuery
from module_higgsfield.entity.vo.element_vo import ElementRevisionCreate
from module_higgsfield.service.element_service import ElementService
from module_higgsfield.service.reference_update_service import ReferenceUpdateService
from tests import test_higgsfield_references as fixtures


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ReferenceUpdateTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = fixtures.ReferenceTests.cleanup_schema
    create = fixtures.ReferenceTests.create
    new_upload = fixtures.ReferenceTests.new_upload
    send_part = fixtures.ReferenceTests.send_part
    ready_upload = fixtures.ReferenceTests.ready_upload
    asyncSetUp = fixtures.ReferenceTests.asyncSetUp

    async def check(self, project_id=None):
        async with self.sessions() as db:
            return await ReferenceUpdateService.check(db, self.owner, ReferenceUpdatesQuery(
                projectId=project_id or self.project_id,
                elementRevisionIds=[self.source['currentRevision']['id']],
            ))

    async def test_current_cross_project_and_deleted(self):
        self.assertEqual((await self.check())['items'][0]['state'], 'current')
        hidden = (await self.check(self.target_id))['items'][0]
        self.assertEqual(hidden['state'], 'unavailable')
        self.assertNotIn('candidate', hidden)
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_element SET del_flag='2' WHERE element_id=:id"),
                             {'id': int(self.source['element']['id'])})
            await db.commit()
        self.assertEqual((await self.check())['items'][0]['state'], 'unavailable')

    async def test_new_revision_is_suggestion_only(self):
        old = self.source['currentRevision']['id']
        async with self.sessions() as db:
            await ElementService.mutate(db, self.owner, int(self.source['element']['id']), 'revisions',
                ElementRevisionCreate(revision=self.source['element']['revision'], description='新修订',
                    media=[{'assetVersionId': self.asset['currentVersionId'], 'ordinal': 0, 'isPrimary': True}]), str(uuid4()))
        result = (await self.check())['items'][0]
        self.assertEqual(result['state'], 'updated')
        self.assertEqual(result['elementRevisionId'], old)
        self.assertNotEqual(result['candidate']['elementRevisionId'], old)
        self.assertEqual(result['candidate']['assetVersionIds'], [self.asset['currentVersionId']])
        self.assertEqual(await self.check(), {'items': [result]})
