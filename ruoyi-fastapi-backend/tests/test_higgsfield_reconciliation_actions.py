"""对账动作验证账号一致、版本冲突、审计及批次联动。"""
import importlib.util
import os
import unittest
from pathlib import Path
from uuid import uuid4
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from exceptions.exception import ServiceWarning, PermissionException
from module_higgsfield.entity.do.usage_do import HfBillingSubject
from module_higgsfield.entity.vo.reconciliation_vo import ReconciliationMatch, ReconciliationConfirm, ReconciliationResolve
from module_higgsfield.service.reconciliation_action_service import ReconciliationActionService as Action
from module_higgsfield.dao.reconciliation_dao import ReconciliationDao as Dao
from module_higgsfield.service.write_service import WriteService
from tests import test_higgsfield_reconciliation_worker as worker


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用独立 schema 测试')
class ReconciliationActionTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = worker.ReconciliationWorkerTests.cleanup_schema
    upload = worker.ReconciliationWorkerTests.upload
    payload = worker.ReconciliationWorkerTests.payload
    submit = worker.ReconciliationWorkerTests.submit

    async def asyncSetUp(self):
        await worker.ReconciliationWorkerTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location('usage_for_reconciliation',
            Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_38_usage_records.py')
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        async with self.engine.begin() as connection:
            def migrate(sync_connection):
                with Operations.context(MigrationContext.configure(sync_connection)):
                    migration.upgrade()
            await connection.run_sync(migrate)
        self.batch_id = await self.submit()
        await self.worker.execute(self.batch_id)
        async with self.sessions() as db:
            self.line_id = await db.scalar(text('SELECT line_id FROM hf_reconciliation_line'))
            subject = await Dao.add(db, HfBillingSubject, account_id=int(self.account_id), cost_center_id=1,
                origin_call_id=1, subject_kind='test', identity_key='test:1', **WriteService.audit(self.owner))
            other = await Dao.add(db, HfBillingSubject, account_id=99999, cost_center_id=1,
                origin_call_id=2, subject_kind='test', identity_key='test:2', **WriteService.audit(self.owner))
            self.subject_id, self.other_id = str(subject.subject_id), str(other.subject_id)
            await db.commit()

    async def test_match_confirm_replay_and_batch_revision(self):
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await Action.save(db, self.owner, self.line_id, 'confirm',
                    ReconciliationConfirm(revision='1', reason='尚未匹配'), str(uuid4()))
            key = str(uuid4())
            payload = ReconciliationMatch(revision='1', subjectId=self.subject_id, reason='核对供应商账单对象')
            first, _ = await Action.save(db, self.owner, self.line_id, 'match', payload, key)
            repeated, replay = await Action.save(db, self.owner, self.line_id, 'match', payload, key)
            self.assertTrue(replay)
            self.assertEqual(first, repeated)
            self.assertEqual(first['data']['revision'], '2')
            with self.assertRaises(ServiceWarning):
                await Action.save(db, self.owner, self.line_id, 'confirm',
                    ReconciliationConfirm(revision='1', reason='旧版本'), str(uuid4()))
            confirmed, _ = await Action.save(db, self.owner, self.line_id, 'confirm',
                ReconciliationConfirm(revision='2', reason='人工核对原始账单'), str(uuid4()))
            self.assertEqual(confirmed['data']['status'], 'confirmed')
            self.assertEqual(await db.scalar(text('SELECT status FROM hf_reconciliation_batch')), '2')
            self.assertEqual(await db.scalar(text('SELECT revision FROM hf_reconciliation_batch')), 4)
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM hf_audit_log WHERE object_type='reconciliation_line'")), 2)
            self.owner.permissions = []
            with self.assertRaises(PermissionException):
                await Action.save(db, self.owner, self.line_id, 'match', payload, key)

    async def test_cross_account_and_disputed_line_refused(self):
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await Action.save(db, self.owner, self.line_id, 'match',
                    ReconciliationMatch(revision='1', subjectId=self.other_id, reason='账号不同'), str(uuid4()))
            self.assertIsNone(await db.scalar(text('SELECT subject_id FROM hf_reconciliation_line')))
        self.body = b'externalLineKey,currency,amount\nkey,USD,9\n'
        revised = await self.submit()
        await self.worker.execute(revised)
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await Action.save(db, self.owner, self.line_id, 'match',
                    ReconciliationMatch(revision='2', subjectId=self.subject_id, reason='存在金额差异'), str(uuid4()))
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM hf_audit_log WHERE object_type='reconciliation_line'")), 0)

    async def test_resolve_preserves_original_then_confirm_and_new_conflict(self):
        self.body = b'externalLineKey,currency,amount\nkey,CNY,9.0000000001\n'
        revised = await self.submit()
        await self.worker.execute(revised)
        async with self.sessions() as db:
            observation_id = await db.scalar(text('SELECT max(observation_id) FROM hf_reconciliation_observation'))
            payload = ReconciliationResolve(revision='2', subjectId=self.subject_id,
                observationId=str(observation_id), reason='核对供应商修订账单，采用当前文件')
            key = str(uuid4())
            for changes in ({'observation_id': '999999'}, {'subject_id': self.other_id}):
                with self.assertRaises(ServiceWarning):
                    await Action.save(db, self.owner, self.line_id, 'resolve', payload.model_copy(update=changes), str(uuid4()))
            result, _ = await Action.save(db, self.owner, self.line_id, 'resolve', payload, key)
            self.assertEqual(result['data']['status'], 'matched')
            self.assertEqual(result['data']['currency'], 'USD')
            self.assertEqual(result['data']['amount'], '1.2500000000')
            self.assertEqual(result['data']['acceptedCurrency'], 'CNY')
            self.assertEqual(result['data']['acceptedAmount'], '9.0000000001')
            self.assertEqual(result['data']['acceptedObservationId'], str(observation_id))
            repeated, replay = await Action.save(db, self.owner, self.line_id, 'resolve', payload, key)
            self.assertTrue(replay)
            self.assertEqual(result, repeated)
            with self.assertRaises(ServiceWarning):
                await Action.save(db, self.owner, self.line_id, 'confirm',
                    ReconciliationConfirm(revision='2', reason='旧快照'), str(uuid4()))
            await Action.save(db, self.owner, self.line_id, 'confirm',
                ReconciliationConfirm(revision='3', reason='确认修订金额'), str(uuid4()))
            self.assertEqual((await db.scalars(text('SELECT DISTINCT status FROM hf_reconciliation_batch'))).all(), ['2'])
            audit = await db.scalar(text("SELECT before_after FROM hf_audit_log WHERE action='resolve'"))
            self.assertIsNone(audit['before']['acceptedObservationId'])
            self.assertEqual(audit['after']['acceptedObservationId'], str(observation_id))
        # 相同采用金额仅追加重复观察；再次变化使人工确认失效，但保留历史采用值。
        self.body = b'externalLineKey,currency,amount\nkey,CNY,9.0000000001\n\n'
        duplicate = await self.submit()
        await self.worker.execute(duplicate)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT status FROM hf_reconciliation_line')), '2')
            self.assertEqual(await db.scalar(text('SELECT outcome FROM hf_reconciliation_observation ORDER BY observation_id DESC LIMIT 1')), 'duplicate')
        self.body = b'externalLineKey,currency,amount\nkey,CNY,10\n'
        disputed = await self.submit()
        await self.worker.execute(disputed)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT status FROM hf_reconciliation_line')), '3')
            self.assertEqual(await db.scalar(text('SELECT accepted_observation_id FROM hf_reconciliation_line')), observation_id)
            self.assertEqual((await db.scalars(text('SELECT DISTINCT status FROM hf_reconciliation_batch'))).all(), ['3'])
