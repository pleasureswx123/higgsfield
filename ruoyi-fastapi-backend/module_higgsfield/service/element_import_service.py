"""项目导入受理和复核读取，文件解析由独立执行流程处理。"""
from common.vo import PageModel
from exceptions.exception import PermissionException
from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.dao.element_import_dao import ElementImportDao as Dao
from module_higgsfield.entity.do.asset_do import HfUploadBinding
from module_higgsfield.entity.do.audit_do import HfAuditLog
from module_higgsfield.entity.do.element_import_do import HfImportJob
from module_higgsfield.service.element_import_formats import MIME_TYPES, parser_version
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.upload_service import UploadService
from module_higgsfield.service.write_service import WriteService


class ElementImportService:
    @staticmethod
    async def authorize(db, user, identity, *, write=False):
        job = await Dao.job(db, identity)
        if job is None:
            WorkspaceService.conflict('IMPORT_NOT_FOUND', '导入批次不存在或无权访问')
        _, _, allowed = await WorkspaceService.authorize(db, user, job.project_id, 'element:import',
                                                       owner_id=job.actor_id, write=write)
        if job.actor_id != user.user.user_id and 'project:edit' not in allowed:
            raise PermissionException(message='仅导入操作者或项目治理人员可以复核')
        return job

    @staticmethod
    def row_result(row):
        return dict(rowNo=row.row_no, sourceLocator=row.source_locator, candidate=row.candidate,
            isSelected=row.is_selected == 'Y', revision=str(row.revision),
            state=('pending', 'succeeded', 'failed')[int(row.state)], issues=row.issues,
            elementId=str(row.element_id) if row.element_id else None)

    @classmethod
    async def get(cls, db, user, identity):
        job = await cls.authorize(db, user, identity)
        report = job.validation_report
        return {'id': str(job.import_id), 'projectId': str(job.project_id), 'revision': str(job.revision),
            'status': ('uploaded', 'validated', 'confirmed', 'finished', 'failed')[int(job.status)],
            'summary': {key: report.get(key, 0) for key in ('total', 'valid', 'invalid')},
            'errors': report.get('errors', [])[:100]}

    @classmethod
    async def rows(cls, db, user, identity, query):
        await cls.authorize(db, user, identity)
        rows, total = await Dao.page_rows(db, identity, query)
        return PageModel(rows=[cls.row_result(row) for row in rows],
            total=total, pageNum=query.page_num, pageSize=query.page_size,
            hasNext=query.page_num * query.page_size < total)

    @staticmethod
    async def create(db, user, payload, key):
        path, data = '/imports/elements', payload.model_dump(by_alias=True)
        try:
            await WriteService.lock(db, user, path, key)
            project, _, _ = await WorkspaceService.authorize(db, user, int(payload.project_id), 'element:import',
                                             write=True, owner_id=user.user.user_id)
            replay = await WriteService.replay(db, user, path, key, data)
            if replay:
                await db.commit()
                return replay, True
            upload = await UploadService.authorize(db, user, int(payload.upload_id), write=True)
            if upload.project_id != int(payload.project_id):
                WorkspaceService.conflict('UPLOAD_PROJECT_MISMATCH', '导入文件不属于目标项目')
            if upload.state != '3':
                WorkspaceService.conflict('UPLOAD_NOT_READY', '导入文件尚未完成校验')
            if await AssetDao.binding(db, upload.upload_id):
                WorkspaceService.conflict('UPLOAD_ALREADY_BOUND', '上传已绑定其他正式记录')
            file = await AssetDao.file(db, upload.completed_file_id)
            if (file is None or file.state != '1' or file.sha256 != upload.verified_sha256
                    or file.byte_size != upload.byte_size or file.mime_type != upload.declared_mime_type):
                WorkspaceService.conflict('FILE_NOT_READY', '导入文件关联或完整性不一致')
            formats = {mime: kind for kind, mime in MIME_TYPES.items()}
            if file.mime_type not in formats:
                WorkspaceService.conflict('IMPORT_FORMAT_UNSUPPORTED', '当前解析器支持CSV、XLSX、TXT、MD、DOCX或PDF')
            audit = WriteService.audit(user)
            job = await AssetDao.add(db, HfImportJob, project_id=int(payload.project_id), actor_id=user.user.user_id,
                source_file_id=file.file_id, schema_version=payload.schema_version, source_format=formats[file.mime_type],
                include_project_name='Y' if payload.include_project_name else 'N', parser_version=parser_version(formats[file.mime_type]),
                validation_report={'projectName': project.project_name},
                idempotency_key=WriteService.digest({'path': path, 'key': key}), **audit)
            await AssetDao.add(db, HfUploadBinding, session_id=upload.upload_id, import_job_id=job.import_id,
                               bound_by=user.user.user_id, **audit)
            result = {'id': str(job.import_id), 'accepted': True, 'state': 'pending'}
            await AssetDao.add(db, HfAuditLog, actor_id=user.user.user_id, actor_kind='user',
                project_id=job.project_id, object_type='element_import', object_id=str(job.import_id), action='create',
                request_id=WriteService.digest({'path': path, 'key': key}), before_after={'after': result}, **audit)
            return await WriteService.finish(db, user, path, key, data, result, 'element_import', job.import_id)
        except Exception:
            await db.rollback()
            raise
