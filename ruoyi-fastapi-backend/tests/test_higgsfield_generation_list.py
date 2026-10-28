"""生成列表分页前授权、筛选与事实汇总。"""

import os
import unittest
from pydantic import ValidationError
from sqlalchemy import text
from module_higgsfield.service.generation_read_service import GenerationReadService
from module_higgsfield.entity.vo.generation_query_vo import GenerationQuery
from module_higgsfield.entity.do.generated_output_do import HfGeneratedOutput
from module_higgsfield.service.write_service import WriteService
from tests import test_higgsfield_generation_snapshot as snapshots


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class GenerationListTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = snapshots.GenerationSnapshotTests.cleanup_schema
    migrate = snapshots.GenerationSnapshotTests.migrate
    job = snapshots.GenerationSnapshotTests.job
    create = snapshots.GenerationSnapshotTests.create
    output = snapshots.GenerationSnapshotTests.output

    async def asyncSetUp(self):
        await snapshots.GenerationSnapshotTests.asyncSetUp(self)
        self.identity = self.job_id
        async with self.sessions() as db:
            await db.execute(text('DELETE FROM hf_generated_output'))
            await db.execute(text("UPDATE hf_creation_job SET orchestration_state='1',upstream_state='0'"))
            self.project_id = await db.scalar(text('SELECT project_id FROM hf_creation_job'))
            db.add(
                self.job(
                    project_id=self.project_id,
                    actor_id=2,
                    idempotency_key='other',
                    orchestration_state='5',
                    upstream_state='3',
                    billing_state='0',
                )
            )
            db.add(self.job(project_id=999, idempotency_key='hidden'))
            db.add(
                HfGeneratedOutput(
                    job_id=self.identity, ordinal=0, kind='image', archive_state='3', **WriteService.audit(self.owner)
                )
            )
            await db.commit()

    async def test_mine_intersects_membership_and_revocation(self):
        async with self.sessions() as db:
            result = await GenerationReadService.listing(db, self.owner, GenerationQuery(scope='mine'))
            self.assertEqual(result.total, 1)
            self.assertEqual(result.rows[0]['id'], str(self.identity))
            self.assertEqual(result.rows[0]['archiveSummary'], dict(total=1, ready=0, failed=1, pending=0))
            await db.execute(text("UPDATE hf_project_member SET status='1'"))
            await db.commit()
            result = await GenerationReadService.listing(db, self.owner, GenerationQuery(scope='mine'))
            self.assertEqual(result.total, 0)

    async def test_card_preview_requires_ready_archive_and_asset_permission(self):
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_generated_output SET archive_state='2',file_id=:file WHERE job_id=:job"), {'file': self.file_id, 'job': self.identity})
            await db.commit()
            result = await GenerationReadService.listing(db, self.owner, GenerationQuery(scope='mine'))
            preview = result.rows[0]['cardPreview']
            self.assertEqual(preview['kind'], 'image')
            self.assertEqual(set(preview), {'outputId', 'revision', 'kind'})
            await db.execute(text("UPDATE hf_stored_file SET state='3' WHERE file_id=:file"), {'file': self.file_id})
            await db.commit()
            result = await GenerationReadService.listing(db, self.owner, GenerationQuery(scope='mine'))
            self.assertNotIn('cardPreview', result.rows[0])
            await db.execute(text("UPDATE hf_stored_file SET state='1' WHERE file_id=:file"), {'file': self.file_id})
            await db.execute(text("DELETE FROM hf_project_role_permission WHERE permission_code='asset:read'"))
            await db.commit()
            result = await GenerationReadService.listing(db, self.owner, GenerationQuery(scope='mine'))
            self.assertEqual(result.total, 1)
            self.assertNotIn('cardPreview', result.rows[0])

    async def test_project_scope_and_stable_paging(self):
        async with self.sessions() as db:
            query = GenerationQuery(projectId=str(self.project_id), pageSize=1)
            first = await GenerationReadService.listing(db, self.owner, query)
            query.page_num = 2
            second = await GenerationReadService.listing(db, self.owner, query)
            self.assertEqual(first.total, 2)
            self.assertTrue(first.has_next)
            self.assertFalse(second.has_next)
            self.assertNotEqual(first.rows[0]['id'], second.rows[0]['id'])
            selected = await GenerationReadService.listing(
                db, self.owner, GenerationQuery(projectId=str(self.project_id), state='finished', kind='image')
            )
            self.assertEqual(selected.total, 1)
            self.assertEqual(selected.rows[0]['billingState'], 'pending')
            self.assertEqual(selected.rows[0]['upstreamState'], 'succeeded')
            created = await db.scalar(
                text('SELECT create_time FROM hf_creation_job WHERE job_id=:id'), {'id': self.identity}
            )
            boundary = await GenerationReadService.listing(
                db,
                self.owner,
                GenerationQuery.model_validate(
                    {
                        'scope': 'mine',
                        'from': created.isoformat(),
                    }
                ),
            )
            self.assertEqual(boundary.total, 1)
            boundary = await GenerationReadService.listing(
                db,
                self.owner,
                GenerationQuery.model_validate(
                    {
                        'scope': 'mine',
                        'to': created.isoformat(),
                    }
                ),
            )
            self.assertEqual(boundary.total, 0)

    async def test_role_scope_is_applied_before_count(self):
        async with self.sessions() as db:
            await db.execute(
                text("UPDATE hf_project_role_permission SET data_scope='own' WHERE permission_code='generation:read'")
            )
            await db.commit()
            result = await GenerationReadService.listing(
                db, self.owner, GenerationQuery(projectId=str(self.project_id))
            )
            self.assertEqual(result.total, 1)
            await db.execute(text("DELETE FROM hf_project_role_permission WHERE permission_code='generation:read'"))
            await db.commit()
            result = await GenerationReadService.listing(
                db, self.owner, GenerationQuery(projectId=str(self.project_id))
            )
            self.assertEqual(result.total, 0)


class GenerationQueryTests(unittest.TestCase):
    def test_scope_and_aware_interval(self):
        for data in (
            {},
            {'scope': 'mine', 'from': '2026-10-27T00:00:00'},
            {'scope': 'mine', 'from': '2026-10-28T00:00:00Z', 'to': '2026-10-27T00:00:00Z'},
            {'scope': 'mine', 'pageSize': 101},
        ):
            with self.assertRaises(ValidationError):
                GenerationQuery.model_validate(data)
