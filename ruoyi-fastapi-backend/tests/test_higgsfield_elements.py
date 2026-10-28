"""元素真实迁移和固定资料校验；不替代尚待接入的页面验收。"""

import importlib.util
import os
import unittest
from pathlib import Path
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from sqlalchemy import inspect, text

from exceptions.exception import ServiceWarning
from module_higgsfield.dao.element_dao import ElementDao
from module_higgsfield.dao.folder_dao import FolderDao
from module_higgsfield.entity.do.element_do import HfElement, HfPropertyDefinition
from module_higgsfield.entity.vo.asset_vo import AssetCreate
from module_higgsfield.entity.vo.element_vo import (
    ElementCreate,
    ElementPatch,
    PropertyDefinitionCreate,
    RevisionContent,
)
from module_higgsfield.service.asset_service import AssetService
from module_higgsfield.service.element_content_service import ElementContentService
from module_higgsfield.service.write_service import WriteService
from tests import test_higgsfield_assets as assets


class ElementInputTests(unittest.TestCase):
    def test_media_and_explicit_identity(self):
        fields = {'projectId': '1', 'name': '人物', 'alias': 'hero', 'category': 'character'}
        self.assertEqual(ElementCreate(**fields).media, [])
        for media in (
            [{'assetVersionId': '1', 'ordinal': 0, 'isPrimary': False}],
            [
                {'assetVersionId': '1', 'ordinal': 0, 'isPrimary': True},
                {'assetVersionId': '1', 'ordinal': 1, 'isPrimary': False},
            ],
            [
                {'assetVersionId': '1', 'ordinal': 0, 'isPrimary': True},
                {'assetVersionId': '2', 'ordinal': 0, 'isPrimary': False},
            ],
            [{'assetVersionId': '1', 'ordinal': 0, 'isPrimary': 'true'}],
        ):
            with self.subTest(media=media), self.assertRaises(ValidationError):
                ElementCreate(**fields, media=media)
        for patch in ({'revision': '1'}, {'revision': '1', 'name': None}, {'revision': '1', 'alias': ' '}):
            with self.assertRaises(ValidationError):
                ElementPatch(**patch)
        self.assertEqual(ElementPatch(revision='1', name='新名').model_fields_set, {'revision', 'name'})

    def test_property_shapes(self):
        for options in ([], ['红', '红'], [' '], [' 红']):
            with self.assertRaises(ValidationError):
                PropertyDefinitionCreate(propertyKey='color', name='颜色', valueType='multi_select', options=options)
        with self.assertRaises(ValidationError):
            PropertyDefinitionCreate(propertyKey='color', name='颜色', valueType='text', options=['红'])
        with self.assertRaises(ValidationError):
            RevisionContent(propertyValues=[{'definitionId': '1', 'definitionVersion': 1, 'value': ['红', '红']}])


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用独立 schema 数据库测试')
class ElementDatabaseTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = assets.AssetDatabaseTests.cleanup_schema
    create = assets.AssetDatabaseTests.create
    new_upload = assets.AssetDatabaseTests.new_upload
    send_part = assets.AssetDatabaseTests.send_part
    ready_upload = assets.AssetDatabaseTests.ready_upload

    async def asyncSetUp(self):
        await assets.AssetDatabaseTests.asyncSetUp(self)
        async with self.engine.begin() as conn:
            path = Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_07_elements.py'
            spec = importlib.util.spec_from_file_location('elements_migration_test', path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            def migrate(sync_conn):
                with Operations.context(MigrationContext.configure(sync_conn)):
                    module.upgrade()

            await conn.run_sync(migrate)
        async with self.sessions() as db:
            self.space_id = (await FolderDao.space(db, int(self.project_id))).space_id

    async def test_schema_comments_constraints_and_no_implicit_grants(self):
        async with self.engine.connect() as conn:

            def inspect_tables(sync_conn):
                inspector = inspect(sync_conn)
                for name in (
                    'hf_element',
                    'hf_element_revision',
                    'hf_element_revision_label',
                    'hf_element_revision_media',
                    'hf_property_definition',
                ):
                    self.assertFalse(inspector.get_foreign_keys(name))
                    self.assertTrue(inspector.get_table_comment(name)['text'])
                    self.assertTrue(all(column.get('comment') for column in inspector.get_columns(name)))

            await conn.run_sync(inspect_tables)
            self.assertEqual(
                await conn.scalar(
                    text("SELECT count(*) FROM hf_project_role_permission WHERE permission_code LIKE 'element:%'")
                ),
                0,
            )

    async def test_fixed_media_and_property_snapshots(self):
        upload_id = await self.ready_upload()
        async with self.sessions() as db:
            response, _ = await AssetService.bind(
                db,
                self.owner,
                AssetCreate(projectId=self.project_id, uploadId=str(upload_id), name='人物原图'),
                str(uuid4()),
            )
            asset = response['data']
        async with self.sessions() as db:
            audit = WriteService.audit(self.owner)
            definition = await ElementDao.add(
                db,
                HfPropertyDefinition,
                space_id=self.space_id,
                property_key='color',
                version_no=1,
                property_name='颜色',
                value_type='multi_select',
                options=['红', '蓝'],
                **audit,
            )
            element = await ElementDao.add(
                db,
                HfElement,
                space_id=self.space_id,
                element_name='人物',
                alias='hero',
                category='character',
                create_user_id=self.owner.user.user_id,
                **audit,
            )
            content = RevisionContent(
                description='第一版',
                media=[{'assetVersionId': asset['currentVersionId'], 'ordinal': 0, 'isPrimary': True}],
                propertyValues=[{'definitionId': str(definition.property_id), 'definitionVersion': 1, 'value': ['红']}],
            )
            snapshots = await ElementContentService.validate(
                db, self.owner, int(self.project_id), self.space_id, content
            )
            first = await ElementContentService.append(db, self.owner, element, content, snapshots, '定稿')
            first_id = first.revision_id
            content.description = '第二版'
            second = await ElementContentService.append(db, self.owner, element, content, snapshots, '修改')
            self.assertEqual(second.revision_no, 2)
            self.assertEqual(element.current_revision_id, second.revision_id)
            await db.commit()
        async with self.sessions() as db:
            result = await ElementContentService.result(db, await ElementDao.revision(db, first_id))
            self.assertEqual(result['description'], '第一版')
            self.assertEqual(result['label'], '定稿')
            self.assertEqual(result['media'][0]['assetVersionId'], asset['currentVersionId'])
            self.assertEqual(result['propertySnapshot'][0]['options'], ['红', '蓝'])
            media_only = RevisionContent(media=result['media'])
            with self.assertRaises(ServiceWarning):
                await ElementContentService.validate(
                    db, self.owner, int(self.project_id), self.space_id + 1, media_only
                )
            await db.execute(text("UPDATE hf_asset SET del_flag='2' WHERE asset_id=:id"), {'id': int(asset['id'])})
            with self.assertRaises(ServiceWarning):
                await ElementContentService.validate(db, self.owner, int(self.project_id), self.space_id, media_only)

    async def test_property_scope_and_legal_options(self):
        async with self.sessions() as db:
            audit = WriteService.audit(self.owner)
            first = await ElementDao.add(
                db,
                HfPropertyDefinition,
                space_id=self.space_id,
                property_key='color',
                version_no=1,
                property_name='颜色',
                value_type='multi_select',
                options=['红'],
                **audit,
            )
            second = await ElementDao.add(
                db,
                HfPropertyDefinition,
                space_id=self.space_id,
                property_key='color',
                version_no=2,
                property_name='颜色',
                value_type='multi_select',
                options=['蓝'],
                **audit,
            )
            cases = [
                [{'definitionId': str(first.property_id), 'definitionVersion': 1, 'value': ['蓝']}],
                [{'definitionId': str(first.property_id), 'definitionVersion': 2, 'value': ['红']}],
                [
                    {'definitionId': str(first.property_id), 'definitionVersion': 1, 'value': ['红']},
                    {'definitionId': str(second.property_id), 'definitionVersion': 2, 'value': ['蓝']},
                ],
            ]
            for values in cases:
                with self.assertRaises(ServiceWarning):
                    await ElementContentService.validate(
                        db, self.owner, int(self.project_id), self.space_id, RevisionContent(propertyValues=values)
                    )
            with self.assertRaises(ServiceWarning):
                await ElementContentService.validate(
                    db,
                    self.owner,
                    int(self.project_id),
                    self.space_id + 1,
                    RevisionContent(
                        propertyValues=[
                            {'definitionId': str(first.property_id), 'definitionVersion': 1, 'value': ['红']}
                        ]
                    ),
                )
