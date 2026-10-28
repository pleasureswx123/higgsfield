"""发送意图与任务状态原子提交，旧凭据不可用时不自动替换。"""

import importlib.util
import os
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from sqlalchemy import text

from exceptions.exception import ServiceWarning
from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.service.generation_accept_service import GenerationAcceptService
from module_higgsfield.service.job_lease_service import JobLeaseService
from module_higgsfield.service.job_transition_service import JobTransitionService
from module_higgsfield.service.provider_submit_intent_service import ProviderSubmitIntentService
from tests import test_higgsfield_generation_pipeline as pipeline


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class SubmitIntentTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = pipeline.GenerationPipelineTests.cleanup_schema
    migrate = pipeline.GenerationPipelineTests.migrate
    job = pipeline.GenerationPipelineTests.job

    async def asyncSetUp(self) -> None:
        await pipeline.GenerationPipelineTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location(
            'intent_calls', pipeline.MIGRATIONS / '20261027_35_provider_calls.py'
        )
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')
        async with self.sessions() as db:
            # 基础项目夹具仅建用户和菜单；发送前复核还需真实的框架授权关联表。
            await db.execute(text("CREATE TABLE sys_role(role_id bigint PRIMARY KEY,status char(1),del_flag char(1))"))
            await db.execute(text('CREATE TABLE sys_user_role(user_id bigint,role_id bigint,PRIMARY KEY(user_id,role_id))'))
            await db.execute(text('CREATE TABLE sys_role_menu(role_id bigint,menu_id bigint,PRIMARY KEY(role_id,menu_id))'))
            await db.execute(text("INSERT INTO sys_role VALUES(2,'0','0')"))
            await db.execute(text('INSERT INTO sys_user_role VALUES(:actor,2)'), {'actor': self.owner.user.user_id})
            await db.execute(text("""INSERT INTO sys_menu(menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time)
                SELECT '生成权限测试',0,0,'','F','1','0','generation:create','test',CURRENT_TIMESTAMP
                WHERE NOT EXISTS(SELECT 1 FROM sys_menu WHERE perms='generation:create')"""))
            await db.execute(text("INSERT INTO sys_role_menu SELECT 2,menu_id FROM sys_menu WHERE perms='generation:create'"))
            await db.commit()
            await GenerationAcceptService.accept(
                db,
                self.owner,
                self.payload,
                str(uuid4()),
                currencies=self.policy.currencies(),
                missing_budget_policy='reject',
            )
            self.lease = (await JobLeaseService.claim(db, 'intent-test', limit=1))[0]
            self.lease = await JobTransitionService.apply(db, self.lease, action='prepare')

    async def test_sending_and_task_commit_together_no_duplicate(self) -> None:
        async with self.sessions() as db:
            updated, identity = await ProviderSubmitIntentService.begin(db, self.lease, 'a' * 64)
            self.assertFalse(db.in_transaction())
            self.assertGreater(identity, 0)
            with self.assertRaises(ServiceWarning):
                await ProviderSubmitIntentService.begin(db, updated, 'a' * 64)
            call = (await db.execute(text('SELECT state,acceptance,request_metadata FROM hf_provider_call'))).one()
            self.assertEqual(call[0:2], ('1', 'unknown'))
            self.assertNotIn('secret', str(call[2]))
            self.assertEqual(await db.scalar(text('SELECT orchestration_state FROM hf_creation_job')), '2')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_task_event')), 3)

    async def test_event_failure_rolls_back_intent_and_revoked_key_rejected(self) -> None:
        async with self.sessions() as db:
            with (
                patch.object(JobEventDao, 'state', AsyncMock(side_effect=RuntimeError('事件故障'))),
                self.assertRaises(RuntimeError),
            ):
                await ProviderSubmitIntentService.begin(db, self.lease, 'a' * 64)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 0)
            self.assertEqual(await db.scalar(text('SELECT orchestration_state FROM hf_creation_job')), '1')
            await db.execute(text("UPDATE hf_credential_version SET state='4'"))
            await db.commit()
            with self.assertRaises(ServiceWarning):
                await ProviderSubmitIntentService.begin(db, self.lease, 'a' * 64)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 0)

    async def test_project_lifecycle_blocks_new_intent_without_rewriting_job_or_budget(self):
        from module_higgsfield.service.project_lifecycle_service import ProjectLifecycleService
        from module_higgsfield.entity.vo.project_vo import ProjectPause, ProjectArchive, ProjectRestore
        for filename in ('20261028_74_project_lifecycle.py', '20261028_75_project_manage.py'):
            spec = importlib.util.spec_from_file_location('intent_lifecycle', pipeline.MIGRATIONS / filename)
            self.migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.migration)
            await self.migrate('upgrade')
        async with self.sessions() as db:
            before = await db.scalar(text('SELECT to_jsonb(j) FROM hf_creation_job j WHERE job_id=:id'), {'id': self.lease.job_id})
            project_id = before['project_id']
            revision = await db.scalar(text('SELECT revision FROM hf_project WHERE project_id=:id'), {'id': project_id})
            ledger = (await db.execute(text('SELECT to_jsonb(l) FROM hf_budget_ledger_entry l ORDER BY entry_id'))).scalars().all()
        for action, restore in (('pause', 'resume'), ('archive', 'restore')):
            async with self.sessions() as db:
                model = ProjectPause if action == 'pause' else ProjectArchive
                result, _ = await ProjectLifecycleService.change(db, self.owner, project_id, action,
                    model(revision=str(revision), reason='发送前停止项目'), str(uuid4()))
                revision = result['data']['revision']
                with self.assertRaises(ServiceWarning) as raised:
                    await ProviderSubmitIntentService.begin(db, self.lease, 'a' * 64)
                self.assertEqual(raised.exception.data['errorCode'], 'PROJECT_READ_ONLY')
                self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 0)
                self.assertEqual(await db.scalar(text('SELECT to_jsonb(j) FROM hf_creation_job j WHERE job_id=:id'), {'id': self.lease.job_id}), before)
                self.assertEqual((await db.execute(text('SELECT to_jsonb(l) FROM hf_budget_ledger_entry l ORDER BY entry_id'))).scalars().all(), ledger)
                result, _ = await ProjectLifecycleService.change(db, self.owner, project_id, restore,
                    ProjectRestore(revision=str(revision)), str(uuid4()))
                revision = result['data']['revision']
                self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 0)
                self.assertEqual(await db.scalar(text('SELECT to_jsonb(j) FROM hf_creation_job j WHERE job_id=:id'), {'id': self.lease.job_id}), before)
        async with self.sessions() as db:
            updated, _ = await ProviderSubmitIntentService.begin(db, self.lease, 'a' * 64)
            with self.assertRaises(ServiceWarning):
                await ProviderSubmitIntentService.begin(db, updated, 'a' * 64)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 1)

    async def test_disabled_removed_and_demoted_actor_cannot_create_submission(self):
        async with self.sessions() as db:
            original = await db.scalar(text('SELECT to_jsonb(j) FROM hf_creation_job j WHERE job_id=:id'), {'id': self.lease.job_id})
            actor = original['actor_id']
            role = await db.scalar(text('SELECT role_id FROM hf_project_member WHERE user_id=:actor AND project_id=:project'), {'actor': actor, 'project': original['project_id']})
        changes = (
            ("UPDATE sys_user SET status='1' WHERE user_id=:actor", "UPDATE sys_user SET status='0' WHERE user_id=:actor"),
            ("UPDATE sys_user SET del_flag='2' WHERE user_id=:actor", "UPDATE sys_user SET del_flag='0' WHERE user_id=:actor"),
            ("UPDATE hf_project_member SET status='1' WHERE user_id=:actor AND project_id=:project", "UPDATE hf_project_member SET status='0' WHERE user_id=:actor AND project_id=:project"),
            ("UPDATE hf_project_member SET role_id=(SELECT role_id FROM hf_project_role WHERE code='viewer') WHERE user_id=:actor AND project_id=:project", "UPDATE hf_project_member SET role_id=:role WHERE user_id=:actor AND project_id=:project"),
            ("UPDATE hf_project_role_permission SET data_scope='own' WHERE role_id=:role AND permission_code='generation:create'", "UPDATE hf_project_role_permission SET data_scope='project' WHERE role_id=:role AND permission_code='generation:create'"),
        )
        for revoke, restore in changes:
            with self.subTest(revoke=revoke):
                async with self.sessions() as db:
                    params = {'actor': actor, 'project': original['project_id'], 'role': role}
                    await db.execute(text(revoke), params); await db.commit()
                    with self.assertRaises(ServiceWarning) as raised:
                        await ProviderSubmitIntentService.begin(db, self.lease, 'a' * 64)
                    self.assertEqual(raised.exception.data['errorCode'], 'GENERATION_ACTOR_UNAVAILABLE')
                    self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 0)
                    self.assertEqual(await db.scalar(text('SELECT to_jsonb(j) FROM hf_creation_job j WHERE job_id=:id'), {'id': self.lease.job_id}), original)
                    await db.execute(text(restore), params); await db.commit()
        async with self.sessions() as db:
            await ProviderSubmitIntentService.begin(db, self.lease, 'a' * 64)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 1)

    async def test_system_role_and_menu_revocation_are_checked_before_sending(self):
        from module_higgsfield.dao.generation_actor_dao import GenerationActorDao
        actor = self.owner.user.user_id
        mutations = (
            ("UPDATE sys_role SET status='1' WHERE role_id=2", "UPDATE sys_role SET status='0' WHERE role_id=2"),
            ("UPDATE sys_role SET del_flag='2' WHERE role_id=2", "UPDATE sys_role SET del_flag='0' WHERE role_id=2"),
            ('DELETE FROM sys_user_role WHERE user_id=:actor', 'INSERT INTO sys_user_role VALUES(:actor,2)'),
            ('DELETE FROM sys_role_menu WHERE role_id=2', "INSERT INTO sys_role_menu SELECT 2,menu_id FROM sys_menu WHERE perms='generation:create'"),
            ("UPDATE sys_menu SET status='1' WHERE perms='generation:create'", "UPDATE sys_menu SET status='0' WHERE perms='generation:create'"),
            ("UPDATE sys_menu SET perms='generation:read' WHERE perms='generation:create'", "UPDATE sys_menu SET perms='generation:create' WHERE menu_id IN (SELECT menu_id FROM sys_role_menu WHERE role_id=2)"),
        )
        async with self.sessions() as db:
            original = await db.scalar(text('SELECT to_jsonb(j) FROM hf_creation_job j WHERE job_id=:id'), {'id': self.lease.job_id})
        for revoke, restore in mutations:
            with self.subTest(revoke=revoke):
                async with self.sessions() as db:
                    await db.execute(text(revoke), {'actor': actor}); await db.commit()
                    with self.assertRaises(ServiceWarning) as raised:
                        await ProviderSubmitIntentService.begin(db, self.lease, 'e' * 64)
                    self.assertEqual(raised.exception.data['errorCode'], 'GENERATION_FUNCTION_REVOKED')
                    self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 0)
                    self.assertEqual(await db.scalar(text('SELECT to_jsonb(j) FROM hf_creation_job j WHERE job_id=:id'), {'id': self.lease.job_id}), original)
                    await db.execute(text(restore), {'actor': actor}); await db.commit()
        async with self.sessions() as db:
            self.assertTrue(await GenerationActorDao.system_access(db, actor))
            # 框架通配菜单授权仍有效；禁用角色不能靠该菜单绕过。
            await db.execute(text("UPDATE sys_menu SET perms='*:*:*' WHERE menu_id IN (SELECT menu_id FROM sys_role_menu WHERE role_id=2)"))
            self.assertTrue(await GenerationActorDao.system_access(db, actor))
            await db.execute(text("UPDATE sys_role SET status='1' WHERE role_id=2"))
            self.assertFalse(await GenerationActorDao.system_access(db, actor))
            # 管理员来自有效角色1，不从用户编号或历史快照推断。
            await db.execute(text("INSERT INTO sys_role VALUES(1,'1','0')"))
            await db.execute(text('INSERT INTO sys_user_role VALUES(:actor,1)'), {'actor': actor})
            self.assertFalse(await GenerationActorDao.system_access(db, actor))
            await db.execute(text("UPDATE sys_role SET status='0' WHERE role_id=1")); await db.commit()
            await ProviderSubmitIntentService.begin(db, self.lease, 'e' * 64)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_provider_call')), 1)
