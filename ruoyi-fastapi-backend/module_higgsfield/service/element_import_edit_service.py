"""候选复核修改与整批诊断在同一锁和事务下更新，解析证据摘要不变。"""
from pydantic import ValidationError
from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.dao.element_import_dao import ElementImportDao as Dao
from module_higgsfield.entity.do.audit_do import HfAuditLog
from module_higgsfield.entity.vo.element_vo import ElementFields
from module_higgsfield.service.element_import_service import ElementImportService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService


class ElementImportEditService:
    @staticmethod
    def diagnostics(rows):
        issues, aliases = {}, {}
        for row in rows:
            try:
                ElementFields.model_validate({key: value for key, value in row.candidate.items() if key != 'schemaVersion'})
                issues[row.row_no] = []
            except ValidationError as error:
                issues[row.row_no] = [{'field': str(item['loc'][0]), 'code': 'ELEMENT_FIELD_INVALID',
                    'message': '字段不符合元素规范，请修正后确认'} for item in
                    error.errors(include_input=False, include_context=False)[:31]]
            alias = row.candidate.get('alias', '').strip()
            if row.is_selected == 'Y' and alias:
                aliases.setdefault(alias, []).append(row.row_no)
        for duplicates in aliases.values():
            if len(duplicates) > 1:
                for number in duplicates:
                    issues[number].append({'field': 'alias', 'code': 'ELEMENT_ALIAS_DUPLICATE',
                        'message': '本批次存在相同别名，请修正或取消选择重复项'})
        return issues

    @classmethod
    async def edit(cls, db, user, identity, row_no, payload, key=None):
        path, data = f'/imports/elements/{identity}/rows/{row_no}', payload.model_dump(by_alias=True)
        try:
            await WriteService.lock(db, user, path, key)
            await ElementImportService.authorize(db, user, identity, write=True)
            job = await Dao.job(db, identity, lock=True)
            replay = await WriteService.replay(db, user, path, key, data, method='PATCH')
            if replay:
                await db.commit()
                return replay, True
            if job.status != '1':
                WorkspaceService.conflict('IMPORT_NOT_EDITABLE', '仅已解析、尚未确认的批次可复核')
            rows = await Dao.locked_rows(db, identity)
            target = next((row for row in rows if row.row_no == row_no), None)
            if target is None:
                WorkspaceService.conflict('IMPORT_ROW_NOT_FOUND', '候选行不存在')
            WorkspaceService.check_revision(target, payload.revision)
            before = ElementImportService.row_result(target)
            candidate = payload.candidate.model_dump(by_alias=True)
            candidate.update(name=candidate['name'].strip(), alias=candidate['alias'].strip(),
                             category=candidate['category'].strip())
            target.candidate, target.is_selected = candidate, 'Y' if payload.is_selected else 'N'
            diagnostics = cls.diagnostics(rows)
            audit = WriteService.audit(user)
            for row in rows:
                issues = diagnostics[row.row_no]
                if row is target or row.issues != issues:
                    row.issues, row.state = issues, '2' if issues else '0'
                    row.error_code = issues[0]['code'] if issues else None
                    row.revision += 1
                    row.update_by, row.update_time = audit['update_by'], audit['update_time']
            invalid = sum(bool(row.issues) for row in rows)
            job.validation_report = job.validation_report | dict(total=len(rows), valid=len(rows)-invalid,
                invalid=invalid, errors=[{'rowNo': row.row_no, **issue} for row in rows for issue in row.issues][:100])
            job.revision += 1
            job.update_by, job.update_time = audit['update_by'], audit['update_time']
            result = ElementImportService.row_result(target) | {'batchRevision': str(job.revision)}
            await AssetDao.add(db, HfAuditLog, actor_id=user.user.user_id, actor_kind='user', project_id=job.project_id,
                object_type='element_import_row', object_id=str(target.row_id), action='edit',
                request_id=WriteService.digest({'path': path, 'key': key}),
                before_after={'before': before, 'after': result}, **audit)
            return await WriteService.finish(db, user, path, key, data, result, 'element_import_row', target.row_id,
                                             method='PATCH')
        except Exception:
            await db.rollback()
            raise
