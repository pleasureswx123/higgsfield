"""任务快照的权限、敏感字段隔离和事件游标一致性。"""

import importlib.util
import asyncio
import os
from pathlib import Path
import unittest
from datetime import UTC, datetime
from sqlalchemy import text
from exceptions.exception import ServiceWarning
from module_higgsfield.service.generation_read_service import GenerationReadService
from module_higgsfield.service.output_archive_service import OutputArchiveService
from module_higgsfield.entity.do.usage_do import HfBillingSubject, HfUsageRecord
from tests import test_higgsfield_output_read as reads


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class GenerationSnapshotTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = reads.OutputReadTests.cleanup_schema
    migrate = reads.OutputReadTests.migrate
    job = reads.OutputReadTests.job
    output = reads.OutputReadTests.output
    create = reads.OutputReadTests.create

    async def asyncSetUp(self):
        await reads.OutputReadTests.asyncSetUp(self)
        for name in (
            '20261027_13_models.py',
            '20261027_16_audit.py',
            '20261027_32_generation_read_permission.py',
            '20261027_35_provider_calls.py',
            '20261027_38_usage_records.py',
            '20261027_40_project_usage_permission.py',
        ):
            spec = importlib.util.spec_from_file_location(
                'snapshot_setup', Path(__file__).resolve().parents[1] / 'alembic/versions' / name
            )
            self.migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.migration)
            await self.migrate('upgrade')
        async with self.sessions() as db:
            await db.execute(
                text(
                    "INSERT INTO hf_model_profile(model_id,connection_id,code,display_name,kind,create_time,update_time) VALUES(1,1,'test','测试模型','image',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                )
            )
            await db.execute(
                text(
                    "INSERT INTO hf_model_profile_version(model_version_id,model_id,version_no,gateway_alias,region,capabilities,create_time,update_time) VALUES(1,1,1,'internal-alias','test','{}'::jsonb,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                )
            )
            self.job_id = await db.scalar(text('SELECT job_id FROM hf_creation_job'))
            await db.execute(text('UPDATE hf_creation_job SET event_sequence=7,revision=8'))
            await db.commit()

    async def test_snapshot_contains_real_output_and_scoped_cursor(self):
        async with self.sessions() as db:
            result = await GenerationReadService.snapshot(db, self.owner, self.job_id)
            self.assertEqual(result['eventCursor'], f'{self.job_id}:7')
            self.assertEqual(result['revision'], '8')
            self.assertEqual(result['model'], dict(id='1', versionId='1', displayName='测试模型'))
            self.assertEqual(result['archiveSummary'], dict(total=1, ready=0, pending=1, failed=0))
            self.assertEqual(result['outputs'][0]['id'], str(self.identity))
            self.assertEqual(result['billingState'], 'pending')
            self.assertEqual(result['usageState'], 'unknown')
            for secret in (
                'credentialVersionId',
                'procurementPriceVersionId',
                'inputSnapshot',
                'internal-alias',
                'source_url_ciphertext',
            ):
                self.assertNotIn(secret, str(result))
            self.assertNotIn('billing', result)

    async def test_usage_evidence_is_scoped_and_conflicting_revisions_are_not_confirmed(self):
        now = datetime.now(UTC)
        audit = dict(create_time=now, update_time=now, create_by='test', update_by='test')
        async with self.sessions() as db:
            subject = HfBillingSubject(
                account_id=1,
                job_id=self.job_id,
                origin_call_id=91,
                subject_kind='generation',
                identity_key='call:91',
                **audit,
            )
            db.add(subject)
            await db.flush()
            self.assertEqual(await GenerationReadService.usage_state(db, self.job_id), 'unknown')
            values = dict(
                subject_id=subject.subject_id,
                call_id=91,
                revision_no=1,
                input_tokens=0,
                output_tokens=0,
                completeness='available',
                source_path='usage',
                parser_version='test',
                is_cumulative='N',
                payload_hash='a' * 64,
                raw_usage={},
                **audit,
            )
            db.add(HfUsageRecord(**values))
            await db.flush()
            snapshot = await GenerationReadService.snapshot(db, self.owner, self.job_id)
            self.assertEqual(snapshot['usageState'], 'available')
            self.assertEqual(snapshot['billingVisibility'], 'hidden')
            self.assertNotIn('billing', snapshot)
            self.assertEqual(await GenerationReadService.usage_state(db, self.job_id + 999), 'unknown')
            db.add(HfUsageRecord(**(values | dict(revision_no=2, output_tokens=10, payload_hash='b' * 64))))
            await db.flush()
            self.assertEqual(await GenerationReadService.usage_state(db, self.job_id), 'partial')

    async def test_snapshot_lock_serializes_archive_event(self):
        async def archive_output():
            async with self.sessions() as writer:
                return await OutputArchiveService.mutate(
                    writer, self.identity, revision=1, action='begin', worker='archiver'
                )

        async with self.sessions() as db:
            before = await GenerationReadService.snapshot(db, self.owner, self.job_id)
            writer = asyncio.create_task(archive_output())
            try:
                done, _ = await asyncio.wait([writer], timeout=0.1)
                self.assertFalse(done)
                self.assertEqual(before['eventCursor'], f'{self.job_id}:7')
                self.assertEqual(before['outputs'][0]['archiveState'], 'not_started')
            finally:
                await db.rollback()
                await asyncio.wait_for(writer, timeout=10)
            after = await GenerationReadService.snapshot(db, self.owner, self.job_id)
            self.assertEqual(after['eventCursor'], f'{self.job_id}:8')
            self.assertEqual(after['outputs'][0]['archiveState'], 'archiving')

    async def test_missing_asset_permission_hides_content_and_removed_member_denied(self):
        async with self.sessions() as db:
            await db.execute(text("DELETE FROM hf_project_role_permission WHERE permission_code='asset:read'"))
            await db.commit()
            result = await GenerationReadService.snapshot(db, self.owner, self.job_id)
            self.assertEqual(result['outputs'], [])
            self.assertEqual(result['outputsVisibility'], 'hidden')
            self.assertEqual(result['archiveSummary']['total'], 1)
            await db.execute(text("UPDATE hf_project_member SET status='1'"))
            await db.commit()
            with self.assertRaises(ServiceWarning):
                await GenerationReadService.snapshot(db, self.owner, self.job_id)

    async def test_source_link_uses_live_scope_without_hiding_current_task(self):
        async with self.sessions() as db:
            project_id = await db.scalar(text('SELECT project_id FROM hf_creation_job WHERE job_id=:id'), {'id': self.job_id})
            source = self.job(project_id=project_id, actor_id=2, idempotency_key='source-task')
            db.add(source)
            await db.flush()
            source_id = str(source.job_id)
            await db.execute(text(
                "UPDATE hf_creation_job SET input_snapshot=jsonb_set(input_snapshot,'{sourceJobId}',to_jsonb(CAST(:source AS text))) WHERE job_id=:id"
            ), {'source': source_id, 'id': self.job_id})
            await db.commit()
        async with self.sessions() as db:
            visible = await GenerationReadService.snapshot(db, self.owner, self.job_id)
            self.assertEqual(visible['sourceJobId'], source_id)
            await db.execute(text("UPDATE hf_project_role_permission SET data_scope='own' WHERE permission_code='generation:read'"))
            await db.commit()
        async with self.sessions() as db:
            hidden = await GenerationReadService.snapshot(db, self.owner, self.job_id)
            self.assertEqual(hidden['id'], str(self.job_id))
            self.assertIsNone(hidden['sourceJobId'])

    async def test_failed_snapshot_projects_sanitized_call_reason(self):
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_creation_job SET orchestration_state='5',upstream_state='4' WHERE job_id=:id"), {'id': self.job_id})
            await db.execute(text("""
                INSERT INTO hf_provider_call(job_id,account_id,credential_version_id,operation,request_hash,
                request_metadata,state,acceptance,http_status,response_metadata,started_time,finished_time,create_time,update_time)
                SELECT job_id,1,credential_version_id,'image',repeat('a',64),'{}'::jsonb,'2','rejected',403,
                '{"message":"secret-provider-key","url":"private-signed-url"}'::jsonb,
                CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP
                FROM hf_creation_job WHERE job_id=:id
            """), {'id': self.job_id})
            await db.commit()
        async with self.sessions() as db:
            result = await GenerationReadService.snapshot(db, self.owner, self.job_id)
            self.assertEqual(result['diagnostic']['code'], 'SUBMISSION_AUTH_REJECTED')
            self.assertNotIn('secret-provider-key', str(result))
            self.assertNotIn('private-signed-url', str(result))
