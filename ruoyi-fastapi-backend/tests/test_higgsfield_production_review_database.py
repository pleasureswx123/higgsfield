"""真实开发库服务验收：独立测试项目，外层事务始终回滚，不改现有项目。"""
import os
import unittest
from datetime import timedelta
from types import SimpleNamespace as NS
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from config.database import DataSourceRegistry
from exceptions.exception import PermissionException, ServiceWarning
from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.entity.do.asset_do import HfAsset, HfAssetVersion, HfFolderEntry, HfStoredFile, HfUploadSession
from module_higgsfield.entity.do.project_do import HfProjectMember, HfProjectRole
from module_higgsfield.entity.vo.asset_vo import AssetVersionCreate
from module_higgsfield.entity.vo.production_vo import ProductionAction, ProductionAssignment
from module_higgsfield.entity.vo.project_vo import ProjectCreate
from module_higgsfield.entity.vo.element_vo import ElementCreate, ElementSave, ElementPatch
from module_higgsfield.dao.element_dao import ElementDao
from module_higgsfield.service.element_service import ElementService
from module_higgsfield.service.asset_service import AssetService
from module_higgsfield.service.production_review_service import ProductionReviewService as Service
from module_higgsfield.service.project_service import ProjectService
from module_higgsfield.service.write_service import WriteService
from utils.time_util import TimezoneUtil


@unittest.skipUnless(os.environ.get('HF_REVIEW_DB_TEST') == '1', '需要显式启用本地数据库验收')
class ProductionReviewDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_assigned_maker_rework_and_version_approval(self):
        engine = DataSourceRegistry.get_async_engine()
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                async with AsyncSession(bind=connection, expire_on_commit=False, join_transaction_mode='create_savepoint') as db:
                    await self.run_workflow(db)
            finally:
                await transaction.rollback()
        await engine.dispose()

    async def run_workflow(self, db):
        users = {}
        for name in ('hf_test_owner', 'hf_test_maker_a', 'hf_test_maker_b'):
            row = (await db.execute(text("SELECT user_id,user_name FROM sys_user WHERE user_name=:name AND status='0' AND del_flag='0'"), {'name': name})).first()
            self.assertIsNotNone(row, f'缺少验收账号 {name}')
            # 系统权限全开，仍需经过真实项目角色及对象范围判断。
            users[name] = NS(permissions=['*:*:*'], user=NS(user_id=row.user_id, user_name=row.user_name))
        owner, viewer, maker = (users[name] for name in ('hf_test_owner', 'hf_test_maker_a', 'hf_test_maker_b'))
        created, _ = await ProjectService.create_project(db, owner, ProjectCreate(name='事务回滚-制作闭环验收'), str(uuid4()))
        project_id, space_id = int(created['data']['id']), int(created['data']['spaceId'])
        roles = {row.code: row.role_id for row in (await db.scalars(select(HfProjectRole))).all()}
        for user, role in ((maker, 'producer'), (viewer, 'viewer')):
            db.add(HfProjectMember(project_id=project_id, user_id=user.user.user_id, role_id=roles[role],
                                   status='0', joined_time=TimezoneUtil.utc_now(), **WriteService.audit(owner)))
        file = await db.scalar(select(HfStoredFile).where(HfStoredFile.state == '1', HfStoredFile.mime_type == 'image/png').limit(1))
        self.assertIsNotNone(file, '验收需要已有归档图片，仅引用文件，不修改原素材')
        file_values = {name: getattr(file, name) for name in ('file_id', 'sha256', 'byte_size', 'mime_type')}
        asset = await AssetDao.add(db, HfAsset, space_id=space_id, asset_name='待制作图片', media_type='image',
                                   create_user_id=owner.user.user_id, **WriteService.audit(owner))
        asset_id = asset.asset_id
        version = await AssetDao.add(db, HfAssetVersion, asset_id=asset_id, version_no=1, file_id=file.file_id,
                                     create_user_id=owner.user.user_id, **WriteService.audit(owner))
        version1 = version.version_id
        asset.current_version_id = version1
        await AssetDao.add(db, HfFolderEntry, space_id=space_id, asset_id=asset_id, **WriteService.audit(owner))
        await db.commit()

        current = await Service.get(db, owner, 'asset', asset_id)
        with self.assertRaises(ServiceWarning):
            await Service.assign(db, owner, 'asset', asset_id,
                                 ProductionAssignment(revision=current['revision'], performerId=str(viewer.user.user_id)), str(uuid4()))
        current = await Service.get(db, owner, 'asset', asset_id)
        await Service.assign(db, owner, 'asset', asset_id,
                             ProductionAssignment(revision=current['revision'], performerId=str(maker.user.user_id)), str(uuid4()))

        async def act(user, action, reason=''):
            state = await Service.get(db, user, 'asset', asset_id)
            payload = ProductionAction(revision=state['revision'], versionId=state['versionId'], action=action, reason=reason)
            return await Service.act(db, user, 'asset', asset_id, payload, str(uuid4()))

        with self.assertRaises(PermissionException):
            await act(viewer, 'start')
        await act(maker, 'start')
        await act(maker, 'submit')
        with self.assertRaises(PermissionException):
            await act(maker, 'approve')
        await act(owner, 'request_changes', '请调整颜色后重新提交')
        await act(maker, 'start')
        await act(maker, 'submit')
        submitted = await Service.get(db, owner, 'asset', asset_id)
        payload = ProductionAction(revision=submitted['revision'], versionId=str(version1), action='approve')
        key = str(uuid4())
        approved, replay = await Service.act(db, owner, 'asset', asset_id, payload, key)
        self.assertFalse(replay)
        replayed, replay = await Service.act(db, owner, 'asset', asset_id, payload, key)
        self.assertTrue(replay)
        self.assertEqual(approved, replayed)
        self.assertTrue(approved['data']['reviewVerified'])
        # 第二个客户端持有相同旧修订但使用新操作键，不能覆盖先完成的审核。
        with self.assertRaises(ServiceWarning) as stale:
            await Service.act(db, owner, 'asset', asset_id, payload, str(uuid4()))
        self.assertEqual(stale.exception.data['errorCode'], 'REVISION_CONFLICT')
        unchanged = await Service.get(db, owner, 'asset', asset_id)
        self.assertEqual(len([row for row in unchanged['history'] if row['action'] == 'approve']), 1)

        # 通过真实上传绑定服务追加新版，验证旧版通过不被继承。
        upload = await AssetDao.add(db, HfUploadSession, owner_id=maker.user.user_id, project_id=project_id,
            purpose='asset', file_name='新版.png', declared_mime_type=file_values['mime_type'],
            byte_size=file_values['byte_size'], part_size=file_values['byte_size'], part_count=1,
            expected_sha256=file_values['sha256'], verified_sha256=file_values['sha256'], state='3',
            completed_file_id=file_values['file_id'], expires_time=TimezoneUtil.utc_now() + timedelta(hours=1),
            **WriteService.audit(maker))
        upload_id = upload.upload_id
        await db.commit()
        current = await Service.get(db, maker, 'asset', asset_id)
        await AssetService.bind(db, maker, AssetVersionCreate(uploadId=str(upload_id), revision=current['revision']), str(uuid4()), asset_id)
        current = await Service.get(db, maker, 'asset', asset_id)
        self.assertEqual(current['workStatus'], 'working')
        self.assertFalse(current['reviewVerified'])
        self.assertNotEqual(current['versionId'], str(version1))
        self.assertEqual(current['approvedVersionId'], str(version1))
        self.assertEqual(current['history'][0]['action'], 'revise')
        await act(maker, 'submit')
        current = await Service.get(db, owner, 'asset', asset_id)
        with self.assertRaises(ServiceWarning):
            await Service.act(db, owner, 'asset', asset_id,
                ProductionAction(revision=current['revision'], versionId=str(version1), action='approve'), str(uuid4()))
        await act(owner, 'approve')
        final = await Service.get(db, owner, 'asset', asset_id)
        self.assertTrue(final['reviewVerified'])
        self.assertEqual(final['versionId'], final['approvedVersionId'])
        self.assertEqual(len([row for row in final['history'] if row['action'] == 'approve']), 2)
        # 元素审核的是定义和固定参考媒体组合；素材通过不自动令元素通过。
        fields = dict(name='测试角色', alias='workflow-role', category='character', description='蓝色服装',
                      media=[{'assetVersionId': final['versionId'], 'ordinal': 0, 'isPrimary': True}])
        created, _ = await ElementService.create(db, owner, ElementCreate(projectId=str(project_id), **fields), str(uuid4()))
        element_id = int(created['data']['element']['id'])
        current = await Service.get(db, owner, 'element', element_id)
        self.assertEqual(current['workStatus'], 'none')
        await Service.assign(db, owner, 'element', element_id,
            ProductionAssignment(revision=current['revision'], performerId=str(maker.user.user_id)), str(uuid4()))
        for user, action in ((maker, 'start'), (maker, 'submit'), (owner, 'approve')):
            current = await Service.get(db, user, 'element', element_id)
            await Service.act(db, user, 'element', element_id,
                ProductionAction(revision=current['revision'], versionId=current['versionId'], action=action), str(uuid4()))
        approved = await Service.get(db, maker, 'element', element_id)
        fields['description'] = '红色服装'
        await ElementService.mutate(db, maker, element_id, 'save', ElementSave(**fields,
            revision=approved['revision'], performerId=str(maker.user.user_id), workStatus='approved'), str(uuid4()))
        current = await Service.get(db, maker, 'element', element_id)
        self.assertEqual(current['workStatus'], 'working')
        self.assertEqual(current['approvedVersionId'], approved['versionId'])
        self.assertNotEqual(current['versionId'], approved['versionId'])
        for action in ('submit', 'approve'):
            current = await Service.get(db, owner, 'element', element_id)
            await Service.act(db, owner, 'element', element_id,
                ProductionAction(revision=current['revision'], versionId=current['versionId'], action=action), str(uuid4()))
        before_category = await Service.get(db, maker, 'element', element_id)
        # 不依赖虚构人物开关的分类变化，也必须使审核失效。
        await ElementService.mutate(db, maker, element_id, 'save', ElementSave(**{**fields, 'category': 'scene'},
            revision=before_category['revision'], performerId=str(maker.user.user_id), workStatus='approved'), str(uuid4()))
        current = await Service.get(db, maker, 'element', element_id)
        self.assertEqual(current['workStatus'], 'working')
        for action in ('submit', 'approve'):
            current = await Service.get(db, owner, 'element', element_id)
            await Service.act(db, owner, 'element', element_id,
                ProductionAction(revision=current['revision'], versionId=current['versionId'], action=action), str(uuid4()))
        before_category = await Service.get(db, maker, 'element', element_id)
        await ElementService.mutate(db, maker, element_id, 'patch',
            ElementPatch(revision=before_category['revision'], category='prop'), str(uuid4()))
        current = await Service.get(db, maker, 'element', element_id)
        self.assertEqual(current['workStatus'], 'working')
        self.assertNotEqual(current['versionId'], before_category['versionId'])
        old_revision = await ElementDao.revision(db, int(before_category['versionId']))
        new_revision = await ElementDao.revision(db, int(current['versionId']))
        self.assertEqual(old_revision.category_snapshot, 'scene')
        self.assertEqual(new_revision.category_snapshot, 'prop')
        for action in ('submit', 'approve'):
            current = await Service.get(db, owner, 'element', element_id)
            await Service.act(db, owner, 'element', element_id,
                ProductionAction(revision=current['revision'], versionId=current['versionId'], action=action), str(uuid4()))
        previous = await Service.get(db, maker, 'element', element_id)
        await ElementService.mutate(db, maker, element_id, 'save', ElementSave(**{**fields, 'category': 'other'},
            isFictionalPerson=False, revision=previous['revision'], performerId=str(maker.user.user_id), workStatus='approved'), str(uuid4()))
        current = await Service.get(db, maker, 'element', element_id)
        self.assertEqual(current['workStatus'], 'working')
        self.assertNotEqual(current['versionId'], previous['versionId'])
        new_revision = await ElementDao.revision(db, int(current['versionId']))
        self.assertEqual(new_revision.category_snapshot, 'other')

        # 转交后旧制作人即使仍持有系统通配权限，也不能继续提交原任务。
        for kind, target_id in (('asset', asset_id), ('element', element_id)):
            state = await Service.get(db, owner, kind, target_id)
            await Service.assign(db, owner, kind, target_id,
                ProductionAssignment(revision=state['revision'], performerId=str(owner.user.user_id)), str(uuid4()))
            state = await Service.get(db, maker, kind, target_id)
            self.assertNotIn('submit', state['allowedActions'])
            action = 'reopen' if state['workStatus'] == 'approved' else 'submit'
            with self.assertRaises(PermissionException):
                await Service.act(db, maker, kind, target_id,
                    ProductionAction(revision=state['revision'], versionId=state['versionId'], action=action), str(uuid4()))

        # 保留分配但撤销项目制作角色，下一次请求必须按新角色拒绝写入。
        state = await Service.get(db, owner, 'element', element_id)
        await Service.assign(db, owner, 'element', element_id,
            ProductionAssignment(revision=state['revision'], performerId=str(maker.user.user_id)), str(uuid4()))
        member = await db.scalar(select(HfProjectMember).where(
            HfProjectMember.project_id == project_id, HfProjectMember.user_id == maker.user.user_id))
        member.role_id = roles['viewer']
        await db.commit()
        state = await Service.get(db, maker, 'element', element_id)
        self.assertNotIn('submit', state['allowedActions'])
        with self.assertRaises(PermissionException):
            await Service.act(db, maker, 'element', element_id,
                ProductionAction(revision=state['revision'], versionId=state['versionId'], action='submit'), str(uuid4()))

        # 移出当前项目后，即便身份仍能访问其他项目且有系统通配权限，也不能读本项目记录。
        removed = await db.scalar(select(HfProjectMember).where(
            HfProjectMember.project_id == project_id, HfProjectMember.user_id == viewer.user.user_id))
        removed.status = '1'
        await db.commit()
        for kind, target_id in (('asset', asset_id), ('element', element_id)):
            with self.assertRaises(ServiceWarning) as denied:
                await Service.get(db, viewer, kind, target_id)
            self.assertEqual(denied.exception.data['errorCode'], 'RESOURCE_NOT_FOUND')
