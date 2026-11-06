"""真实隔离 PostgreSQL 验证合并状态授权、终态跟踪和批量查询成本，无供应商调用。"""
import os
import unittest
from sqlalchemy import event, text
from exceptions.exception import PermissionException, ServiceWarning
from module_higgsfield.entity.vo.generation_query_vo import GenerationActivityQuery
from module_higgsfield.service.generation_activity_service import GenerationActivityService
from tests import test_higgsfield_generation_list as listing


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class GenerationActivityTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = listing.GenerationListTests.cleanup_schema
    migrate = listing.GenerationListTests.migrate
    job = listing.GenerationListTests.job
    create = listing.GenerationListTests.create
    output = listing.GenerationListTests.output
    asyncSetUp = listing.GenerationListTests.asyncSetUp

    async def read(self, db, **values):
        return await GenerationActivityService.read(db, self.owner,
            GenerationActivityQuery(projectId=str(self.project_id), **values))

    async def test_scopes_terminal_tracking_and_revocation(self):
        async with self.sessions() as db:
            await db.execute(text("DELETE FROM hf_generated_output"))
            await db.execute(text("UPDATE hf_creation_job SET orchestration_state='1',upstream_state='0'"))
            await db.commit()
            other = await db.scalar(text('SELECT job_id FROM hf_creation_job WHERE actor_id=2'))
            hidden = await db.scalar(text('SELECT job_id FROM hf_creation_job WHERE project_id=999'))
            result = await self.read(db, trackedIds=f'{self.identity},{other},{hidden}')
            self.assertEqual(result['projectActiveCount'], 2)
            self.assertEqual([row['id'] for row in result['rows']], [str(self.identity)])
            await db.execute(text("INSERT INTO hf_project_member(project_id,user_id,role_id,joined_time,create_time,update_time) SELECT :project,2,role_id,NOW(),NOW(),NOW() FROM hf_project_role WHERE code='producer'"), {'project':self.project_id})
            await db.commit()
            # 二十个独立会话并发读取，两名制作用户的个人状态不得串用。
            import asyncio
            from copy import deepcopy
            producer = deepcopy(self.owner)
            producer.user.user_id = 2
            async def concurrent_read(user):
                async with self.sessions() as session:
                    return await GenerationActivityService.read(session, user,
                        GenerationActivityQuery(projectId=str(self.project_id), trackedIds=f'{self.identity},{other},{hidden}'))
            concurrent = await asyncio.gather(*(concurrent_read(self.owner if index % 2 == 0 else producer) for index in range(20)))
            for index, snapshot in enumerate(concurrent):
                self.assertEqual([row['id'] for row in snapshot['rows']], [str(self.identity if index % 2 == 0 else other)])
            await db.execute(text("UPDATE hf_creation_job SET orchestration_state='5',upstream_state='3' WHERE job_id=:id"), {'id':self.identity})
            await db.commit()
            result = await self.read(db, trackedIds=str(self.identity))
            self.assertEqual(result['projectActiveCount'], 1)
            self.assertEqual(result['rows'][0]['orchestrationState'], 'finished')
            self.assertNotIn('inputSnapshot', result['rows'][0])
            self.assertNotIn('billingSummary', result['rows'][0])
            self.assertEqual((await self.read(db))['rows'], [])
            await db.execute(text("UPDATE hf_project_member SET role_id=(SELECT role_id FROM hf_project_role WHERE code='producer') WHERE user_id=1"))
            await db.execute(text("UPDATE hf_project_role_permission SET data_scope='own' WHERE permission_code='generation:read'"))
            await db.commit()
            self.assertEqual((await self.read(db))['projectActiveCount'], 0)
            await db.execute(text("UPDATE hf_project_member SET status='1'"))
            await db.commit()
            with self.assertRaises((PermissionException, ServiceWarning)):
                await self.read(db, trackedIds=str(self.identity))

    async def test_query_count_does_not_grow_per_task_and_pages_cover_all(self):
        async with self.sessions() as db:
            await db.execute(text('DELETE FROM hf_generated_output'))
            statements = []
            def record(conn, cursor, statement, parameters, context, executemany):
                statements.append(statement)
            connection = await db.connection()
            event.listen(connection.sync_connection, 'before_cursor_execute', record)
            await self.read(db)
            baseline = len(statements)
            for index in range(105):
                db.add(self.job(project_id=self.project_id, idempotency_key=f'activity-{index}'))
            await db.flush()
            statements.clear()
            first = await self.read(db)
            self.assertEqual(len(statements), baseline)
            self.assertTrue(first['hasNext'])
            self.assertEqual(len(first['rows']), 100)
            second = await self.read(db, pageNum=2)
            self.assertFalse(second['hasNext'])
            self.assertEqual(len({row['id'] for row in first['rows'] + second['rows']}), 106)
            self.assertFalse(any('FOR UPDATE' in sql or 'FOR SHARE' in sql for sql in statements))
            event.remove(connection.sync_connection, 'before_cursor_execute', record)


class ActivityQueryTests(unittest.TestCase):
    def test_tracking_input_is_bounded(self):
        from pydantic import ValidationError
        for ids in ('0', '1,abc', '9223372036854775808', ','.join(['1'] * 101)):
            with self.assertRaises(ValidationError):
                GenerationActivityQuery(projectId='2', trackedIds=ids)
