"""选中候选整批确认，复用元素创建规则，全部成功或回滚。"""
from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.dao.element_import_dao import ElementImportDao as Dao
from module_higgsfield.entity.do.audit_do import HfAuditLog
from module_higgsfield.entity.vo.element_vo import ElementCreate
from module_higgsfield.service.element_import_service import ElementImportService
from module_higgsfield.service.element_import_edit_service import ElementImportEditService
from module_higgsfield.service.element_service import ElementService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService


class ElementImportConfirmService:
    @staticmethod
    async def confirm(db, user, identity, payload, key):
        path, data = f'/imports/elements/{identity}/confirm', payload.model_dump(by_alias=True)
        try:
            await WriteService.lock(db, user, path, key)
            initial = await ElementImportService.authorize(db, user, identity, write=True)
            await WorkspaceService.authorize(db, user, initial.project_id, 'element:create',
                                             write=True, owner_id=user.user.user_id)
            job = await Dao.job(db, identity, lock=True)
            replay = await WriteService.replay(db, user, path, key, data)
            if replay:
                await db.commit()
                return replay, True
            # 批次保留永久确认回执，通用幂等记录清理后也不能重复创建。
            confirmation = job.validation_report.get('confirmation')
            if job.status == '3' and confirmation:
                if confirmation['sourceRevision'] != payload.revision:
                    WorkspaceService.conflict('REVISION_CONFLICT', '确认版本与已完成批次不一致')
                return await WriteService.finish(db, user, path, key, data, confirmation['receipt'],
                                                'element_import', identity)
            WorkspaceService.check_revision(job, payload.revision)
            if job.status != '1':
                WorkspaceService.conflict('IMPORT_NOT_CONFIRMABLE', '仅已解析且尚未确认的批次允许确认')
            rows = await Dao.locked_rows(db, identity)
            selected = [row for row in rows if row.is_selected == 'Y']
            if not selected:
                WorkspaceService.conflict('IMPORT_SELECTION_EMPTY', '请至少选择一个候选')
            diagnostics = ElementImportEditService.diagnostics(selected)
            if any(diagnostics.values()):
                WorkspaceService.conflict('IMPORT_CANDIDATES_INVALID', '选中候选仍有字段或重复别名错误')
            audit = WriteService.audit(user)
            for row in selected:
                candidate = {name: value for name, value in row.candidate.items() if name != 'schemaVersion'}
                creation = ElementCreate.model_validate(candidate | {'projectId': str(job.project_id)})
                result = await ElementService.create_in_transaction(db, user, creation)
                row.element_id, row.state = int(result['element']['id']), '1'
                row.issues, row.error_code = [], None
                row.revision += 1
                row.update_by, row.update_time = audit['update_by'], audit['update_time']
            job.status, job.revision = '3', job.revision + 1
            job.update_by, job.update_time = audit['update_by'], audit['update_time']
            receipt = {'id': str(identity), 'accepted': True, 'state': 'finished',
                       'revision': str(job.revision), 'createdCount': len(selected)}
            job.validation_report = job.validation_report | {'confirmation': {
                'sourceRevision': payload.revision, 'receipt': receipt}}
            await AssetDao.add(db, HfAuditLog, actor_id=user.user.user_id, actor_kind='user', project_id=job.project_id,
                object_type='element_import', object_id=str(identity), action='confirm',
                request_id=WriteService.digest({'path': path, 'key': key}),
                before_after={'sourceRevision': payload.revision, 'after': receipt}, **audit)
            return await WriteService.finish(db, user, path, key, data, receipt, 'element_import', identity)
        except Exception:
            await db.rollback()
            raise
