"""私有草稿迁移、所有者边界、并发控制和引用原子保存。"""

import importlib.util
import os
import unittest
from pathlib import Path
from uuid import uuid4
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from exceptions.exception import ServiceWarning
from module_higgsfield.entity.vo.draft_vo import DraftCreate, DraftUpdate, DraftQuery
from module_higgsfield.service.draft_service import DraftService
from tests import test_higgsfield_references as references


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class DraftTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = references.ReferenceTests.cleanup_schema
    create = references.ReferenceTests.create
    new_upload = references.ReferenceTests.new_upload
    send_part = references.ReferenceTests.send_part
    ready_upload = references.ReferenceTests.ready_upload

    async def test_private_listing_filters_before_pagination_and_revocation(self):
        await self.make()
        second, _ = await self.make()
        async with self.sessions() as db:
            # 模拟另一成员的合法草稿，管理员仍不能在本人目录中看见。
            await db.execute(
                text("""INSERT INTO hf_prompt_draft(project_id,owner_id,kind,body,schema_version,revision,create_time,update_time)
                SELECT project_id,2,kind,body,schema_version,revision,NOW(),NOW() FROM hf_prompt_draft WHERE draft_id=:id"""),
                {'id': int(second['data']['id'])},
            )
            await db.commit()
            result = await DraftService.listing(db, self.owner, DraftQuery(projectId=self.project_id, pageSize=1))
            self.assertEqual(result.total, 2)
            self.assertTrue(result.has_next)
            self.assertEqual(result.rows[0]['id'], second['data']['id'])
            self.assertIn('[引用]', result.rows[0]['promptExcerpt'])
            self.assertNotIn('body', result.rows[0])
            self.assertEqual(
                (await DraftService.listing(db, self.owner, DraftQuery(projectId=self.project_id, kind='video'))).total,
                0,
            )
            await db.execute(
                text("UPDATE hf_project_member SET status='1' WHERE project_id=:id AND user_id=1"),
                {'id': int(self.project_id)},
            )
            await db.commit()
            with self.assertRaises(ServiceWarning):
                await DraftService.listing(db, self.owner, DraftQuery(projectId=self.project_id))

    async def asyncSetUp(self):
        await references.ReferenceTests.asyncSetUp(self)
        async with self.engine.begin() as conn:
            spec = importlib.util.spec_from_file_location(
                'draft_migration', Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_12_drafts.py'
            )
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)

            def migrate(sync_conn):
                with Operations.context(MigrationContext.configure(sync_conn)):
                    migration.upgrade()

            await conn.run_sync(migrate)
        for name in ('20261027_13_models.py', '20261027_15_provider_accounts.py'):
            spec = importlib.util.spec_from_file_location(
                'draft_model_dependency', Path(__file__).resolve().parents[1] / 'alembic/versions' / name
            )
            dependency = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(dependency)
            async with self.engine.begin() as conn:

                def migrate_dependency(sync_conn):
                    with Operations.context(MigrationContext.configure(sync_conn)):
                        dependency.upgrade()

                await conn.run_sync(migrate_dependency)

    def content(self):
        return {
            'body': {
                'prompt': {
                    'content': [
                        {'content': [{'type': 'text', 'text': '私有提示词'}, {'type': 'mention', 'referenceKey': '1'}]}
                    ]
                }
            },
            'references': [
                {
                    'referenceKey': '1',
                    'assetVersionId': self.asset['currentVersionId'],
                    'elementRevisionId': self.source['currentRevision']['id'],
                    'mediaRole': 'reference_image',
                    'ordinal': 0,
                }
            ],
        }

    async def make(self, key=None):
        async with self.sessions() as db:
            return await DraftService.save(
                db,
                self.owner,
                DraftCreate(projectId=self.project_id, kind='image', **self.content()),
                key or str(uuid4()),
            )

    async def test_private_owner_and_atomic_update(self):
        result, _ = await self.make()
        draft = result['data']
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await DraftService.get(db, self.other, int(draft['id']))
        update = DraftUpdate(
            revision='1',
            body={'prompt': {'content': [{'content': [{'type': 'text', 'text': '无图草稿'}]}]}},
            references=[],
        )
        async with self.sessions() as db:
            saved, _ = await DraftService.save(db, self.owner, update, str(uuid4()), int(draft['id']))
            self.assertEqual(saved['data']['revision'], '2')
            self.assertEqual(saved['data']['references'], [])
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_draft_reference')), 0)
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await DraftService.save(db, self.owner, update, str(uuid4()), int(draft['id']))
        async with self.sessions() as db:
            current = await DraftService.get(db, self.owner, int(draft['id']))
            self.assertEqual(current['body']['prompt']['content'][0]['content'][0]['text'], '无图草稿')

    async def test_replay_and_failed_reference_keep_previous_body(self):
        key = str(uuid4())
        result, _ = await self.make(key)
        repeated, replayed = await self.make(key)
        self.assertTrue(replayed)
        self.assertEqual(result, repeated)
        draft_id = int(result['data']['id'])
        invalid = self.content()
        invalid['references'][0]['assetVersionId'] = '999999'
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await DraftService.save(db, self.owner, DraftUpdate(revision='1', **invalid), str(uuid4()), draft_id)
        async with self.sessions() as db:
            current = await DraftService.get(db, self.owner, draft_id)
            self.assertEqual(current['revision'], '1')
            self.assertEqual(current['references'][0]['assetVersionId'], self.asset['currentVersionId'])
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_prompt_draft')), 1)

    async def test_project_readonly_and_database_contract(self):
        result, _ = await self.make()
        async with self.sessions() as db:
            await db.execute(
                text("UPDATE hf_project SET status='1' WHERE project_id=:id"), {'id': int(self.project_id)}
            )
            await db.commit()
        async with self.sessions() as db:
            self.assertEqual((await DraftService.get(db, self.owner, int(result['data']['id'])))['revision'], '1')
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await DraftService.save(
                    db, self.owner, DraftUpdate(revision='1', **self.content()), str(uuid4()), int(result['data']['id'])
                )
        async with self.sessions() as db:
            self.assertEqual(
                await db.scalar(
                    text(
                        "SELECT count(*) FROM pg_constraint WHERE conrelid IN ('hf_prompt_draft'::regclass,'hf_draft_reference'::regclass) AND contype='f'"
                    )
                ),
                0,
            )
            self.assertEqual(
                await db.scalar(
                    text(
                        "SELECT count(*) FROM pg_attribute WHERE attrelid IN ('hf_prompt_draft'::regclass,'hf_draft_reference'::regclass) AND attnum>0 AND NOT attisdropped AND col_description(attrelid,attnum) IS NULL"
                    )
                ),
                0,
            )
