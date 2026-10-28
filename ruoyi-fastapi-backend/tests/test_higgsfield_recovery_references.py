"""恢复引用核验使用真实迁移和隔离PostgreSQL，不修补故障数据。"""

import os
import importlib.util
from pathlib import Path
import unittest
from sqlalchemy import text
from module_higgsfield.service.recovery_reference_service import RecoveryReferenceService
from tests import test_higgsfield_output_read as reads


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class RecoveryReferenceTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = reads.OutputReadTests.cleanup_schema
    migrate = reads.OutputReadTests.migrate
    job = reads.OutputReadTests.job
    output = reads.OutputReadTests.output
    create = reads.OutputReadTests.create
    async def asyncSetUp(self):
        await reads.OutputReadTests.asyncSetUp(self)
        spec = importlib.util.spec_from_file_location(
            'recovery_elements', Path(__file__).resolve().parents[1] / 'alembic/versions/20261027_07_elements.py')
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')
        spec = importlib.util.spec_from_file_location(
            'recovery_derivatives', Path(__file__).resolve().parents[1] / 'alembic/versions/20261028_76_media_derivatives.py')
        self.migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.migration)
        await self.migrate('upgrade')

    async def test_missing_cross_owner_and_historical_references_are_detected(self):
        clean = await RecoveryReferenceService.audit(self.sessions)
        self.assertEqual(clean['failed'], 0)
        async with self.sessions() as db:
            assets = []
            for name in ('恢复素材甲', '恢复素材乙'):
                assets.append(await db.scalar(text(
                    "INSERT INTO hf_asset(space_id,asset_name,media_type,create_user_id,del_flag,create_time,update_time) "
                    "VALUES(1,:name,'image',1,'2',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP) RETURNING asset_id"
                ), {'name': name}))
            versions = []
            for owner, file_id in ((assets[0], self.file_id), (assets[1], 999999), (999999, self.file_id)):
                versions.append(await db.scalar(text(
                    'INSERT INTO hf_asset_version(asset_id,version_no,file_id,create_user_id,create_time,update_time) '
                    'VALUES(:owner,1,:file,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP) RETURNING version_id'
                ), {'owner': owner, 'file': file_id}))
            await db.execute(text('UPDATE hf_asset SET current_version_id=:version WHERE asset_id=:id'),
                             {'version': versions[1], 'id': assets[0]})
            await db.execute(text('UPDATE hf_asset_version SET source_asset_version_id=999999 WHERE version_id=:id'),
                             {'id': versions[1]})
            await db.execute(text('UPDATE hf_asset_version SET source_output_id=999999 WHERE version_id=:id'),
                             {'id': versions[2]})
            await db.execute(text("UPDATE hf_stored_file SET state='3'"))
            await db.execute(text("UPDATE hf_generated_output SET job_id=999999,file_id=:file,archive_state='2',del_flag='2'"),
                             {'file': self.file_id})
            db.add(self.output(job_id=999999, ordinal=1, file_id=999999, archive_state='2', del_flag='2'))
            await db.commit()
        report = await RecoveryReferenceService.audit(self.sessions)
        self.assertEqual(report['rulesChecked'], 21)
        self.assertTrue(all(value > 0 for key, value in report['counts'].items() if key.startswith(('asset_', 'output_'))), report)
        self.assertEqual(report['failed'], sum(report['counts'].values()))
        self.assertTrue(all(isinstance(row['recordId'], str) for row in report['failures']))
        self.assertNotIn('恢复素材甲', str(report))
        capped = await RecoveryReferenceService.audit(self.sessions, sample_limit=1)
        self.assertEqual(capped['failed'], report['failed'])
        self.assertEqual(len(capped['failures']), 1)
        self.assertTrue(capped['failuresTruncated'])
        empty_sample = await RecoveryReferenceService.audit(self.sessions, sample_limit=0)
        self.assertEqual(empty_sample['counts'], report['counts'])
        self.assertEqual(empty_sample['failures'], [])
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT current_version_id FROM hf_asset WHERE asset_id=:id'),
                                            {'id': assets[0]}), versions[1])
            self.assertEqual(await db.scalar(text('SELECT state FROM hf_stored_file WHERE file_id=:id'),
                                            {'id': self.file_id}), '3')

    async def test_element_revision_media_and_primary_integrity(self):
        async with self.sessions() as db:
            asset = await db.scalar(text(
                "INSERT INTO hf_asset(space_id,asset_name,media_type,create_user_id,create_time,update_time) "
                "VALUES(1,'恢复图','image',1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP) RETURNING asset_id"
            ))
            version = await db.scalar(text(
                'INSERT INTO hf_asset_version(asset_id,version_no,file_id,create_user_id,create_time,update_time) '
                'VALUES(:asset,1,:file,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP) RETURNING version_id'
            ), {'asset': asset, 'file': self.file_id})
            elements, revisions = [], []
            for alias in ('restore-a', 'restore-b'):
                element = await db.scalar(text(
                    "INSERT INTO hf_element(space_id,element_name,alias,category,create_user_id,del_flag,create_time,update_time) "
                    "VALUES(1,'恢复元素',:alias,'character',1,'2',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP) RETURNING element_id"
                ), {'alias': alias})
                revision = await db.scalar(text(
                    'INSERT INTO hf_element_revision(element_id,revision_no,create_user_id,create_time,update_time) '
                    'VALUES(:element,1,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP) RETURNING revision_id'
                ), {'element': element})
                await db.execute(text('UPDATE hf_element SET current_revision_id=:revision WHERE element_id=:element'),
                                 {'revision': revision, 'element': element})
                elements.append(element)
                revisions.append(revision)
            await db.execute(text(
                "INSERT INTO hf_element_revision_media(element_revision_id,asset_version_id,ordinal,is_primary,create_time,update_time) "
                "VALUES(:revision,:version,0,'Y',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
            ), {'revision': revisions[0], 'version': version})
            await db.commit()
        # 无图修订合法，逻辑删除但关系完整的历史也不误报。
        self.assertEqual((await RecoveryReferenceService.audit(self.sessions))['failed'], 0)
        async with self.sessions() as db:
            await db.execute(text('UPDATE hf_element SET current_revision_id=:revision WHERE element_id=:element'),
                             {'revision': revisions[1], 'element': elements[0]})
            await db.execute(text('UPDATE hf_asset SET space_id=2 WHERE asset_id=:asset'), {'asset': asset})
            await db.execute(text("UPDATE hf_element_revision_media SET is_primary='N'"))
            await db.execute(text(
                'INSERT INTO hf_element_revision(element_id,revision_no,create_user_id,create_time,update_time) '
                'VALUES(999999,1,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)'
            ))
            await db.execute(text(
                "INSERT INTO hf_element_revision_label(element_revision_id,label,update_user_id,create_time,update_time) "
                "VALUES(999999,'丢失修订标签',1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
            ))
            for revision, asset_version in ((999999, version), (revisions[1], 999999)):
                await db.execute(text(
                    "INSERT INTO hf_element_revision_media(element_revision_id,asset_version_id,ordinal,is_primary,create_time,update_time) "
                    "VALUES(:revision,:version,0,'Y',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                ), {'revision': revision, 'version': asset_version})
            await db.commit()
        report = await RecoveryReferenceService.audit(self.sessions)
        element_counts = {key: value for key, value in report['counts'].items() if key.startswith('element_')}
        self.assertEqual(len(element_counts), 7)
        self.assertTrue(all(value == 1 for value in element_counts.values()), report)
        self.assertNotIn('丢失修订标签', str(report))
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT current_revision_id FROM hf_element WHERE element_id=:id'),
                                            {'id': elements[0]}), revisions[1])

    async def test_derivative_recovery_detects_missing_unavailable_and_invalid_files_without_writes(self):
        async with self.sessions() as db:
            files = []
            for index in range(3):
                files.append(await db.scalar(text(
                    "INSERT INTO hf_stored_file(storage_key,sha256,byte_size,mime_type,width,height,state,create_time,update_time) "
                    "VALUES (:key,:hash,128,'image/webp',128,64,'1',now(),now()) RETURNING file_id"),
                    {'key': f'media/{index + 800:032x}', 'hash': 'a' * 64}))
            for source, derived, recipe in (
                (self.file_id, None, 'pending-check'),
                (self.file_id, files[0], 'image-thumbnail-v1'),
                (self.file_id, files[1], 'unavailable-check'),
                (files[2], None, 'source-check'),
                (self.file_id, None, 'missing-check'),
            ):
                await db.execute(text(
                    "INSERT INTO hf_media_derivative(source_file_id,derived_file_id,recipe,state,next_action_time,create_time,update_time) "
                    "VALUES (:source,:derived,:recipe,:state,now(),now(),now())"),
                    {'source': source, 'derived': derived, 'recipe': recipe, 'state': '2' if derived else '0'})
            await db.commit()
        self.assertEqual((await RecoveryReferenceService.audit(self.sessions))['failed'], 0)
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_media_derivative SET source_file_id=999999 WHERE recipe='pending-check'"))
            await db.execute(text("UPDATE hf_media_derivative SET derived_file_id=999998,state='2' WHERE recipe='missing-check'"))
            await db.execute(text("UPDATE hf_stored_file SET state='2' WHERE file_id IN (:first,:second)"),
                             {'first': files[1], 'second': files[2]})
            await db.execute(text('UPDATE hf_stored_file SET width=513 WHERE file_id=:id'), {'id': files[0]})
            await db.commit()
            before = (await db.execute(text('SELECT * FROM hf_media_derivative ORDER BY derivative_id'))).all()
        report = await RecoveryReferenceService.audit(self.sessions, sample_limit=2)
        self.assertEqual(report['failed'], 5, report)
        self.assertTrue(all(value == 1 for key, value in report['counts'].items() if key.startswith('derivative_')), report)
        self.assertEqual(len(report['failures']), 2)
        self.assertTrue(report['failuresTruncated'])
        self.assertNotIn('storage_key', str(report))
        async with self.sessions() as db:
            self.assertEqual((await db.execute(text('SELECT * FROM hf_media_derivative ORDER BY derivative_id'))).all(), before)
            self.assertEqual(await db.scalar(text('SELECT width FROM hf_stored_file WHERE file_id=:id'), {'id': files[0]}), 513)
