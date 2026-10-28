"""候选复核的版本联动、选中集合别名校验与审计回滚。"""
import os
import unittest
from unittest.mock import patch, AsyncMock
from uuid import uuid4
from sqlalchemy import text
from exceptions.exception import ServiceWarning, PermissionException
from module_higgsfield.entity.vo.element_import_vo import ElementImportRowEdit, ElementImportRowsQuery
from module_higgsfield.service.element_import_edit_service import ElementImportEditService
from module_higgsfield.service.element_import_service import ElementImportService
from module_higgsfield.service.element_import_worker_service import ElementImportWorker
from module_higgsfield.dao.asset_dao import AssetDao
from tests import test_higgsfield_element_import_worker as worker


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class ElementImportEditTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = worker.ElementImportWorkerTests.cleanup_schema
    create = worker.ElementImportWorkerTests.create
    migrate = worker.ElementImportWorkerTests.migrate
    send_part = worker.ElementImportWorkerTests.send_part
    upload = worker.ElementImportWorkerTests.upload
    accept = worker.ElementImportWorkerTests.accept

    async def asyncSetUp(self):
        await worker.ElementImportWorkerTests.asyncSetUp(self)
        self.identity = await self.accept('名称,别名,分类,描述\n角色甲,a,角色,说明\n角色乙,a,角色,说明'.encode())
        await ElementImportWorker(self.sessions, self.storage).execute(self.identity)
        async with self.sessions() as db:
            self.rows = (await ElementImportService.rows(db, self.owner, self.identity, ElementImportRowsQuery())).rows

    async def edit(self, number, payload, key):
        async with self.sessions() as db:
            return await ElementImportEditService.edit(db, self.owner, self.identity, number, payload, key)

    async def test_selection_recomputes_duplicates_and_invalidates_other_row_revision(self):
        payload = ElementImportRowEdit(revision='1', candidate=self.rows[1]['candidate'], isSelected=False)
        key = str(uuid4())
        first, repeated = await self.edit(2, payload, key)
        self.assertFalse(repeated)
        self.assertEqual(first['data']['batchRevision'], '3')
        second, repeated = await self.edit(2, payload, key)
        self.assertTrue(repeated)
        self.assertEqual(first, second)
        async with self.sessions() as db:
            rows = (await ElementImportService.rows(db, self.owner, self.identity, ElementImportRowsQuery())).rows
            self.assertEqual([row['revision'] for row in rows], ['2', '2'])
            self.assertEqual([row['issues'] for row in rows], [[], []])
            report = await db.scalar(text('SELECT validation_report FROM hf_import_job'))
            self.assertTrue(report['parseHash'])
            self.assertEqual(report['invalid'], 0)
        with self.assertRaises(ServiceWarning):
            await self.edit(1, ElementImportRowEdit(revision='1', candidate=self.rows[0]['candidate'], isSelected=True), str(uuid4()))
        changed = dict(rows[0]['candidate'], name='人工修正名称')
        result, _ = await self.edit(1, ElementImportRowEdit(revision='2', candidate=changed, isSelected=True), str(uuid4()))
        self.assertEqual(result['data']['candidate']['name'], '人工修正名称')
        self.owner.permissions = []
        with self.assertRaises(PermissionException):
            await self.edit(2, payload, key)

    async def test_audit_failure_rolls_back_all_rows_and_frozen_batch_rejects_edit(self):
        payload = ElementImportRowEdit(revision='1', candidate=self.rows[1]['candidate'], isSelected=False)
        with patch.object(AssetDao, 'add', AsyncMock(side_effect=RuntimeError('审计写入失败'))):
            with self.assertRaises(RuntimeError):
                await self.edit(2, payload, str(uuid4()))
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT revision FROM hf_import_job')), 2)
            self.assertEqual(await db.scalar(text("SELECT count(*) FROM hf_import_row WHERE revision=1 AND is_selected='Y'")), 2)
            await db.execute(text("UPDATE hf_import_job SET status='3'"))
            await db.commit()
        with self.assertRaises(ServiceWarning):
            await self.edit(2, payload, str(uuid4()))
