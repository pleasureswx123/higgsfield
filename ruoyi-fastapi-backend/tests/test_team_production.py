"""多人制作共享队列与名额：独立 PostgreSQL schema，不接触真实供应商。"""
import asyncio
import os
import unittest
from uuid import uuid4
from unittest.mock import AsyncMock, patch
from sqlalchemy import text
from exceptions.exception import ServiceWarning
from module_higgsfield.service.generation_accept_service import GenerationAcceptService
from module_higgsfield.service.job_lease_service import JobLeaseService
from module_higgsfield.service.production_policy_service import ProductionPolicyService
from module_higgsfield.dao.production_capacity_dao import ProductionCapacityDao
from module_higgsfield.dao.provider_call_dao import ProviderCallDao
from tests import test_higgsfield_provider_submit_intent as intent


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class TeamProductionTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = intent.SubmitIntentTests.cleanup_schema
    migrate = intent.SubmitIntentTests.migrate
    job = intent.SubmitIntentTests.job
    asyncSetUp = intent.SubmitIntentTests.asyncSetUp

    async def test_unknown_capacity_expires_once_without_resubmit_or_fact_change(self):
        from datetime import timedelta
        from module_higgsfield.service.provider_submit_intent_service import ProviderSubmitIntentService
        from module_higgsfield.service.unknown_capacity_service import UnknownCapacityService
        async with self.sessions() as db:
            self.lease, call_id = await ProviderSubmitIntentService.begin(db, self.lease, 'a' * 64)
            await db.execute(text("UPDATE hf_creation_job SET orchestration_state='3',upstream_state='6',next_action_time=NULL,lease_owner=NULL,lease_until=NULL"))
            await db.execute(text("UPDATE hf_provider_call SET state='3',finished_time=clock_timestamp()"))
            await db.commit()
            now = await db.scalar(text('SELECT clock_timestamp()'))
            self.assertEqual(await UnknownCapacityService.recover(db, now, 'recovery-test'), 0)
            self.assertFalse(await ProductionCapacityDao.acquire(db, self.key_id, now))
            # 配置允许最长七天，使用八天后的时钟验证所有保护条件都已满足。
            future = now + timedelta(days=8)
            self.assertEqual(await UnknownCapacityService.recover(db, future, 'recovery-test'), 1)
            self.assertEqual(await UnknownCapacityService.recover(db, future, 'recovery-test'), 0)
            self.assertTrue(await ProductionCapacityDao.acquire(db, self.key_id, future))
            from module_higgsfield.dao.production_policy_dao import ProductionPolicyDao
            self.assertEqual(tuple(await ProductionPolicyDao.queue_counts(db, 1, self.project_id)), (0, 0, 0))
            self.assertEqual((await db.execute(text('SELECT state,acceptance,http_status FROM hf_provider_call'))).one(), ('3','unknown',None))
            self.assertEqual((await db.execute(text('SELECT orchestration_state,upstream_state,next_action_time FROM hf_creation_job'))).one(), ('3','6',None))
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM hf_audit_log WHERE action='release_unknown_capacity'")), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 1)
            await db.rollback()
            self.assertIsNone(await db.scalar(text("SELECT request_metadata->>'capacityReleasedAt' FROM hf_provider_call")))

    async def test_unknown_capacity_never_reclaims_live_or_reconciling_job(self):
        from datetime import timedelta
        from module_higgsfield.service.provider_submit_intent_service import ProviderSubmitIntentService
        from module_higgsfield.service.unknown_capacity_service import UnknownCapacityService
        async with self.sessions() as db:
            self.lease, _ = await ProviderSubmitIntentService.begin(db, self.lease, 'a' * 64)
            await db.execute(text("UPDATE hf_creation_job SET orchestration_state='3',upstream_state='6',next_action_time=clock_timestamp(),lease_owner=NULL,lease_until=NULL"))
            await db.execute(text("UPDATE hf_provider_call SET state='3',finished_time=clock_timestamp()"))
            await db.commit()
            now = await db.scalar(text('SELECT clock_timestamp()'))
            future = now + timedelta(days=8)
            self.assertEqual(await UnknownCapacityService.recover(db, future, 'recovery-test'), 0)
            await db.execute(text("UPDATE hf_creation_job SET next_action_time=NULL,lease_owner='live-worker',lease_until=:until"), {'until':future+timedelta(seconds=60)})
            self.assertEqual(await UnknownCapacityService.recover(db, future, 'recovery-test'), 0)

    async def test_invalid_response_test_capacity_is_recovered_but_sending_is_not(self):
        from datetime import timedelta
        from module_higgsfield.service.unknown_capacity_service import UnknownCapacityService
        async with self.sessions() as db:
            now = await db.scalar(text('SELECT clock_timestamp()'))
            for state in ('1', '2', '3'):
                await ProviderCallDao.add(db, dict(account_id=int(self.account_id), cost_center_id=1,
                    credential_version_id=self.key_id, operation='test', request_hash='a'*64,
                    state=state, acceptance='unknown', request_metadata={}, started_time=now,
                    finished_time=None if state == '1' else now))
            await db.commit()
            self.assertEqual(await UnknownCapacityService.recover(db, now+timedelta(days=8), 'test-recovery'), 2)
            self.assertEqual(await UnknownCapacityService.recover(db, now+timedelta(days=8), 'test-recovery'), 0)
            self.assertIsNone(await db.scalar(text("SELECT request_metadata->>'capacityReleasedAt' FROM hf_provider_call WHERE state='1'")))
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM hf_audit_log WHERE action='release_unknown_capacity'")), 2)

    async def test_user_rotation_and_member_removal_preserve_isolation(self):
        from copy import deepcopy
        producer = deepcopy(self.owner)
        producer.user.user_id, producer.user.user_name = 2, '测试制作人'
        producer.permissions = ['project:read', 'generation:create']
        async with self.sessions() as db:
            await db.execute(text("INSERT INTO hf_project_member(project_id,user_id,role_id,joined_time,create_time,update_time) SELECT :project,2,role_id,NOW(),NOW(),NOW() FROM hf_project_role WHERE code='producer'"), {'project':self.project_id})
            await db.execute(text('INSERT INTO sys_user_role VALUES(2,2)'))
            await db.execute(text('UPDATE hf_routing_policy SET max_concurrency=2'))
            await db.execute(text("UPDATE hf_creation_job SET orchestration_state='0',lease_owner=NULL,lease_until=NULL,next_action_time=clock_timestamp()"))
            await db.commit()
        key = str(uuid4())
        async with self.sessions() as db:
            result, replayed = await GenerationAcceptService.accept(db, producer, self.payload, key,
                currencies=self.policy.currencies(), missing_budget_policy='allow')
            self.assertFalse(replayed)
            producer_job = int(result['data']['id'])
        async with self.sessions() as db:
            for _ in range(8):
                db.add(self.job(actor_id=1, project_id=self.project_id, credential_version_id=self.key_id,
                               idempotency_key=str(uuid4())))
            await db.flush()
            await db.execute(text('UPDATE hf_creation_job SET next_action_time=clock_timestamp()'))
            await db.commit()
            leases = await JobLeaseService.claim(db, 'fair-team', limit=2)
            self.assertEqual(len(leases), 2)
            self.assertIn(producer_job, [lease.job_id for lease in leases])
            await db.execute(text('UPDATE hf_project_member SET status=\'1\' WHERE user_id=2'))
            await db.commit()
        async with self.sessions() as db:
            with self.assertRaises(ServiceWarning):
                await GenerationAcceptService.accept(db, producer, self.payload, key,
                    currencies=self.policy.currencies(), missing_budget_policy='allow')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_creation_job WHERE actor_id=2')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 0)

    async def test_rotation_and_conflicting_routes_share_strict_limit_other_key_continues(self):
        from sqlalchemy import select
        from module_higgsfield.entity.do.credential_do import HfProviderCredential, HfCredentialVersion
        from module_higgsfield.entity.do.routing_do import HfRoutingPolicy
        from module_higgsfield.service.write_service import WriteService
        async with self.sessions() as db:
            original = await db.get(HfCredentialVersion, self.key_id)
            values = {c.name: getattr(original, c.name) for c in HfCredentialVersion.__table__.columns if not c.primary_key}
            rotated = HfCredentialVersion(**(values | {'version_no': 2, 'nonce': os.urandom(12)}))
            db.add(rotated)
            await db.flush()
            now = await db.scalar(text('SELECT clock_timestamp()'))
            self.assertFalse(await ProductionCapacityDao.acquire(db, rotated.credential_version_id, now))
            await db.execute(text('UPDATE hf_routing_policy SET max_concurrency=3'))
            self.assertTrue(await ProductionCapacityDao.acquire(db, rotated.credential_version_id, now))
            db.add(HfRoutingPolicy(project_provider_config_id=9999, credential_id=original.credential_id,
                max_concurrency=1, enabled='Y', **WriteService.audit(self.owner)))
            await db.flush()
            self.assertFalse(await ProductionCapacityDao.acquire(db, rotated.credential_version_id, now))
            other = HfProviderCredential(account_id=int(self.account_id),credential_name='独立测试凭据',owner_id=1,
                **WriteService.audit(self.owner))
            db.add(other)
            await db.flush()
            independent = HfCredentialVersion(**(values | {'credential_id': other.credential_id,'nonce':os.urandom(12)}))
            db.add(independent)
            await db.flush()
            self.assertTrue(await ProductionCapacityDao.acquire(db, independent.credential_version_id, now))
            await db.commit()

    async def test_policy_migration_preserves_settings_and_invalid_values_fail_closed(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('production_migration',
            intent.pipeline.MIGRATIONS / '20261105_88_production_capacity.py')
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        async with self.sessions() as db:
            await db.execute(text("INSERT INTO sys_config(config_key,config_value) VALUES ('hf.production.userPending','7')"))
            await db.commit()
        await self.migrate('upgrade')
        async with self.sessions() as db:
            policy = await ProductionPolicyService.read(db)
            self.assertEqual(policy['userPending'], 7)
            self.assertEqual(policy['platformPending'], 1000)
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM pg_indexes WHERE schemaname=current_schema() AND indexname IN ('ix_hf_job_pending_scope','ix_hf_test_call_capacity')")), 2)
            await db.execute(text("UPDATE sys_config SET config_value='0' WHERE config_key='hf.production.userPending'"))
            with self.assertRaises(ServiceWarning):
                await ProductionPolicyService.read(db)
            await db.rollback()
        await self.migrate('downgrade')

    async def test_video_tracking_window_pauses_without_network(self):
        from module_higgsfield.service.videoplus_poll_handler import VideoPlusPollHandler
        from module_higgsfield.service.generation_worker_service import JobExecutionContext
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_creation_job SET orchestration_state='4',upstream_state='2',upstream_task_id='mock-task',create_time=clock_timestamp()-interval '3 hours'"))
            await db.commit()
        context = JobExecutionContext(self.sessions, self.lease, 60)
        with patch('module_higgsfield.service.videoplus_poll_handler.ProviderHttpService.from_versions') as transport:
            await VideoPlusPollHandler()(context)
            transport.assert_not_called()
        async with self.sessions() as db:
            self.assertEqual((await db.execute(text('SELECT orchestration_state,upstream_state,next_action_time,lease_until FROM hf_creation_job'))).one(), ('4', '2', None, None))
            self.assertFalse(await ProductionCapacityDao.acquire(db, self.key_id, await db.scalar(text('SELECT clock_timestamp()'))))

    async def test_concurrent_admission_limits_and_full_queue_idempotency(self):
        async with self.sessions() as db:
            await db.execute(text("INSERT INTO sys_config(config_key,config_value) VALUES ('hf.production.userPending','5')"))
            await db.commit()
        keys = [str(uuid4()) for _ in range(12)]

        async def submit(key):
            async with self.sessions() as db:
                try:
                    return await GenerationAcceptService.accept(db, self.owner, self.payload, key,
                        currencies=self.policy.currencies(), missing_budget_policy='allow')
                except ServiceWarning as exc:
                    return exc.data['errorCode']

        results = await asyncio.gather(*(submit(key) for key in keys))
        accepted = [(key, result) for key, result in zip(keys, results) if not isinstance(result, str)]
        self.assertEqual(len(accepted), 4)  # 基础夹具已有一个待处理任务。
        self.assertEqual(results.count('GENERATION_QUEUE_FULL'), 8)
        repeats = await asyncio.gather(*(submit(accepted[0][0]) for _ in range(8)))
        self.assertTrue(all(row == 'IDEMPOTENCY_IN_PROGRESS' or row[1] is True for row in repeats))
        replayed = [row for row in repeats if not isinstance(row, str)]
        self.assertTrue(replayed)
        self.assertEqual({row[0]['data']['id'] for row in replayed}, {accepted[0][1][0]['data']['id']})
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_creation_job')), 5)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 0)

    async def test_multi_user_project_limits_are_atomic(self):
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_creation_job SET orchestration_state='5',lease_owner=NULL,lease_until=NULL"))
            await db.execute(text("INSERT INTO sys_config(config_key,config_value) VALUES "
                "('hf.production.userPending','3'),('hf.production.projectPending','7'),('hf.production.platformPending','10')"))
            await db.commit()

        async def submit(index):
            actor, project = index % 8 + 10, index % 2 + 100
            async with self.sessions() as db:
                try:
                    await ProductionPolicyService.admit(db, actor, project)
                    db.add(self.job(actor_id=actor, project_id=project, idempotency_key=str(uuid4()),
                                    credential_version_id=self.key_id))
                    await db.commit()
                    return True
                except ServiceWarning:
                    await db.rollback()
                    return False

        results = await asyncio.gather(*(submit(index) for index in range(40)))
        self.assertEqual(sum(results), 10)
        async with self.sessions() as db:
            rows = (await db.execute(text("SELECT actor_id,project_id,count(*) FROM hf_creation_job WHERE orchestration_state='0' GROUP BY actor_id,project_id"))).all()
            self.assertTrue(all(row[2] <= 3 for row in rows))
            self.assertTrue(all(sum(r[2] for r in rows if r[1] == project) <= 7 for project in (100, 101)))

    async def test_generation_and_test_claim_same_slots_across_workers(self):
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_creation_job SET orchestration_state='0',lease_owner=NULL,lease_until=NULL,next_action_time=clock_timestamp()"))
            await db.execute(text('UPDATE hf_routing_policy SET max_concurrency=2'))
            for index in range(12):
                db.add(self.job(actor_id=index % 4 + 10, project_id=index % 2 + 100,
                    idempotency_key=str(uuid4()), credential_version_id=self.key_id))
            await db.flush()
            await db.execute(text('UPDATE hf_creation_job SET next_action_time=clock_timestamp()'))
            await db.commit()

        async def test_claim():
            async with self.sessions() as db:
                now = await db.scalar(text('SELECT clock_timestamp()'))
                granted = await ProductionCapacityDao.acquire(db, self.key_id, now)
                if granted:
                    await ProviderCallDao.add(db, dict(account_id=int(self.account_id), cost_center_id=1,
                        credential_version_id=self.key_id, operation='test', request_hash='a'*64,
                        state='1', acceptance='unknown', request_metadata={}, response_metadata={}, started_time=now))
                await db.commit()
                return granted

        async def generate(worker):
            async with self.sessions() as db:
                return await JobLeaseService.claim(db, worker, limit=10)

        results = await asyncio.gather(test_claim(), test_claim(), generate('team-a'), generate('team-b'))
        used = sum(results[:2]) + sum(len(rows) for rows in results[2:])
        self.assertLessEqual(used, 2)
        # 再次领取不能穿透已经持久化的名额。
        extra = await asyncio.gather(test_claim(), generate('team-c'))
        self.assertLessEqual(used + int(extra[0]) + len(extra[1]), 2)

    async def test_unknown_pause_keeps_capacity_until_explicit_release(self):
        from module_higgsfield.service.video_reconciliation_handler import VideoReconciliationHandler
        from module_higgsfield.service.generation_worker_service import JobExecutionContext
        from module_higgsfield.service.provider_submit_intent_service import ProviderSubmitIntentService
        async with self.sessions() as db:
            self.lease, call_id = await ProviderSubmitIntentService.begin(db, self.lease, 'a'*64)
            await db.execute(text("UPDATE hf_creation_job SET orchestration_state='3',upstream_state='6'"))
            await db.execute(text("UPDATE hf_provider_call SET state='3',finished_time=clock_timestamp()"))
            await db.commit()
        context = JobExecutionContext(self.sessions, self.lease, 60)
        with patch('module_higgsfield.service.video_reconciliation_handler.ProviderResponseDao.for_call', AsyncMock(return_value=None)):
            await VideoReconciliationHandler(None)(context)
        async with self.sessions() as db:
            row = (await db.execute(text('SELECT orchestration_state,next_action_time,lease_owner FROM hf_creation_job'))).one()
            self.assertEqual(tuple(row), ('3', None, None))
            now = await db.scalar(text('SELECT clock_timestamp()'))
            self.assertFalse(await ProductionCapacityDao.acquire(db, self.key_id, now))
            await db.execute(text("UPDATE hf_creation_job SET orchestration_state='6'"))
            # 单纯改变本地状态仍不释放名额，必须存在显式核查记录。
            self.assertFalse(await ProductionCapacityDao.acquire(db, self.key_id, now))
            await db.execute(text("UPDATE hf_provider_call SET request_metadata=request_metadata || '{\"capacityReleasedAt\":\"verified\"}'::jsonb"))
            self.assertTrue(await ProductionCapacityDao.acquire(db, self.key_id, now))
            await db.commit()
