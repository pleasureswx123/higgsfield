"""跨项目复制双向授权与固定来源证据。"""

import importlib.util
import os
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import AsyncMock, patch
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from exceptions.exception import PermissionException, ServiceWarning
from module_higgsfield.dao.element_dao import ElementDao
from module_higgsfield.dao.folder_dao import FolderDao
from module_higgsfield.entity.vo.element_vo import ElementCreate, ElementCopy, PropertyDefinitionCreate
from module_higgsfield.entity.vo.asset_vo import AssetCreate
from module_higgsfield.service.asset_service import AssetService
from module_higgsfield.service.element_service import ElementService
from module_higgsfield.service.element_copy_service import ElementCopyService
from tests import test_higgsfield_element_service as service_tests
from tests import test_higgsfield_assets as asset_tests


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用独立 schema 数据库测试')
class ElementCopyTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = service_tests.ElementServiceTests.cleanup_schema
    create = service_tests.ElementServiceTests.create
    new_upload = asset_tests.AssetDatabaseTests.new_upload
    send_part = asset_tests.AssetDatabaseTests.send_part
    ready_upload = asset_tests.AssetDatabaseTests.ready_upload

    async def asyncSetUp(self):
        await service_tests.ElementServiceTests.asyncSetUp(self)
        async with self.engine.begin() as conn:
            path = Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_09_content_copy.py'
            spec = importlib.util.spec_from_file_location('copy_migration_test', path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            def migrate(sync_conn):
                with Operations.context(MigrationContext.configure(sync_conn)):
                    module.upgrade()

            await conn.run_sync(migrate)
        target, _ = await self.create(name='目标项目')
        self.target_id = target['data']['id']
        upload_id = await self.ready_upload()
        async with self.sessions() as db:
            asset, _ = await AssetService.bind(
                db,
                self.owner,
                AssetCreate(projectId=self.project_id, uploadId=str(upload_id), name='原图'),
                str(uuid4()),
            )
            self.asset = asset['data']
        async with self.sessions() as db:
            element, _ = await ElementService.create(
                db,
                self.owner,
                ElementCreate(
                    projectId=self.project_id,
                    name='原角色',
                    alias='hero',
                    category='character',
                    media=[{'assetVersionId': self.asset['currentVersionId'], 'ordinal': 0, 'isPrimary': True}],
                ),
                str(uuid4()),
            )
            self.source = element['data']

    def payload(self):
        return ElementCopy(
            targetProjectId=self.target_id, sourceRevisionId=self.source['currentRevision']['id'], alias='hero_copy'
        )

    async def test_copy_new_identity_same_file_provenance_and_replay(self):
        key, payload = str(uuid4()), self.payload()
        async with self.sessions() as db:
            result, _ = await ElementCopyService.copy(db, self.owner, int(self.source['element']['id']), payload, key)
        async with self.sessions() as db:
            replay, repeated = await ElementCopyService.copy(
                db, self.owner, int(self.source['element']['id']), payload, key
            )
            self.assertTrue(repeated)
            self.assertEqual(result, replay)
            self.assertNotEqual(result['data']['id'], self.source['element']['id'])
            detail = await ElementService.detail(db, self.owner, int(result['data']['id']))
            copied_version = detail['currentRevision']['media'][0]['assetVersionId']
            self.assertNotEqual(copied_version, self.asset['currentVersionId'])
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_stored_file')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_asset')), 2)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_content_copy')), 2)
            self.assertEqual(
                await db.scalar(
                    text('SELECT source_asset_version_id FROM hf_asset_version WHERE version_id=:id'),
                    {'id': int(copied_version)},
                ),
                int(self.asset['currentVersionId']),
            )

    async def test_missing_source_use_rolls_back_without_target_rows(self):
        async with self.sessions() as db:
            await db.execute(text("DELETE FROM hf_project_role_permission WHERE permission_code='asset:reference'"))
            await db.commit()
        async with self.sessions() as db:
            with self.assertRaises(PermissionException):
                await ElementCopyService.copy(
                    db, self.owner, int(self.source['element']['id']), self.payload(), str(uuid4())
                )
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_element')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_asset')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_content_copy')), 0)

    async def test_property_collision_does_not_overwrite_target_definition(self):
        for project_id, options in ((self.project_id, ['红']), (self.target_id, ['蓝'])):
            async with self.sessions() as db:
                result, _ = await ElementService.write_definition(
                    db,
                    self.owner,
                    PropertyDefinitionCreate(
                        propertyKey='color', name='颜色', valueType='multi_select', options=options
                    ),
                    str(uuid4()),
                    project_id=int(project_id),
                )
                if project_id == self.project_id:
                    source_definition = result['data']['id']
        async with self.sessions() as db:
            element, _ = await ElementService.create(
                db,
                self.owner,
                ElementCreate(
                    projectId=self.project_id,
                    name='带属性角色',
                    alias='properties',
                    category='character',
                    propertyValues=[{'definitionId': source_definition, 'definitionVersion': 1, 'value': ['红']}],
                ),
                str(uuid4()),
            )
        async with self.sessions() as db:
            result, _ = await ElementCopyService.copy(
                db,
                self.owner,
                int(element['data']['element']['id']),
                ElementCopy(
                    targetProjectId=self.target_id,
                    sourceRevisionId=element['data']['currentRevision']['id'],
                    alias='properties_copy',
                ),
                str(uuid4()),
            )
            detail = await ElementService.detail(db, self.owner, int(result['data']['id']))
            snapshot = detail['currentRevision']['propertySnapshot'][0]
            self.assertEqual(snapshot['value'], ['红'])
            self.assertTrue(snapshot['propertyKey'].startswith('copy_'))
            space = await FolderDao.space(db, int(self.target_id))
            unchanged = await ElementDao.latest_definition(db, space.space_id, 'color')
            self.assertEqual(unchanged.options, ['蓝'])

    async def test_partial_copy_failure_rolls_back_all_new_records(self):
        with patch.object(ElementCopyService, 'evidence', AsyncMock(side_effect=RuntimeError('模拟复制证据写入失败'))):
            async with self.sessions() as db:
                with self.assertRaises(RuntimeError):
                    await ElementCopyService.copy(
                        db, self.owner, int(self.source['element']['id']), self.payload(), str(uuid4())
                    )
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_asset')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_asset_version')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_folder_entry')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_element')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_content_copy')), 0)
