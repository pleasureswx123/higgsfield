"""内部解析结果登记：候选与摘要同事务提交，不创建正式元素。"""
from module_higgsfield.dao.element_import_dao import ElementImportDao as Dao
from module_higgsfield.service.element_import_parser_service import ElementImportParserService as Parser
from module_higgsfield.service.element_import_formats import supports_version, MIME_TYPES
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService
from utils.time_util import TimezoneUtil


class ElementImportResultService:
    @staticmethod
    def validate(rows, source_format):
        if not isinstance(rows, list) or not 1 <= len(rows) <= 10000:
            Parser.fail(0, '候选集合为空或超过限制')
        clean, previous = [], (0, 0) if source_format in {'docx', 'pdf'} else 0
        for ordinal, row in enumerate(rows, 1):
            if type(row.row_no) is not int or row.row_no != ordinal:
                Parser.fail(0, '候选序号必须连续且从1开始')
            locator = row.source_locator
            expected = ({'sheet', 'row'} if source_format == 'xlsx' else {'paragraph', 'line'}
                        if source_format == 'docx' else {'page', 'line'} if source_format == 'pdf' else {'line'})
            if not isinstance(locator, dict) or set(locator) != expected:
                Parser.fail(0, '候选来源定位与文件格式不一致')
            position = locator.get('line', locator.get('row'))
            if source_format in {'docx', 'pdf'}:
                paragraph = locator['paragraph' if source_format == 'docx' else 'page']
                if type(paragraph) is not int or paragraph <= 0 or type(position) is not int or position <= 0:
                    Parser.fail(0, '来源段落或行号无效')
                position = (paragraph, position)
            elif type(position) is not int:
                Parser.fail(0, '来源行号无效')
            if position <= previous:
                Parser.fail(0, '来源行号必须严格递增')
            if source_format == 'xlsx' and (not isinstance(locator['sheet'], str) or not locator['sheet']
                    or len(locator['sheet']) > 31):
                Parser.fail(0, '工作表名称无效')
            candidate = row.candidate
            if (not isinstance(candidate, dict) or set(candidate) != {*Parser.columns, 'schemaVersion', 'propertyValues'}
                    or type(candidate['schemaVersion']) is not int or candidate['schemaVersion'] != 1
                    or candidate['propertyValues'] != []):
                Parser.fail(0, '模板候选结构无效')
            item = Parser.candidate([candidate[key] for key in Parser.columns], ordinal, dict(locator),
                                    project_name='', include_project_name=False)
            if item.candidate != candidate:
                Parser.fail(0, '候选不是规范化解析结果')
            clean.append(item)
            previous = position
        Parser.finish(clean)
        if any(item.issues != original.issues for item, original in zip(clean, rows)):
            Parser.fail(0, '候选诊断与字段校验结果不一致')
        return clean

    @classmethod
    async def apply(cls, db, identity, rows, *, source_file_id, parser_version):
        """调用方须在文件IO后传入原文件身份，锁内再次核对批次固定配置。"""
        try:
            job = await Dao.job(db, identity, lock=True)
            if job is None:
                WorkspaceService.conflict('IMPORT_NOT_FOUND', '导入批次不存在')
            if (type(source_file_id) is not int or source_file_id != job.source_file_id
                    or parser_version != job.parser_version or not supports_version(job.source_format, parser_version)
                    or job.schema_version != 1 or job.source_format not in MIME_TYPES):
                WorkspaceService.conflict('IMPORT_SOURCE_CHANGED', '来源文件或解析配置不一致')
            clean = cls.validate(rows, job.source_format)
            digest = WriteService.digest([{'rowNo': row.row_no, 'sourceLocator': row.source_locator,
                                          'candidate': row.candidate, 'issues': row.issues} for row in clean])
            count = await Dao.count_rows(db, identity)
            if job.status != '0' or count:
                if (job.status in {'1', '2', '3'} and job.validation_report.get('parseHash') == digest
                        and count == len(clean)):
                    # 重试只核对原解析摘要，不能覆盖人工已编辑的候选。
                    await db.commit()
                    return False
                WorkspaceService.conflict('IMPORT_RESULT_CONFLICT', '导入结果已经登记或状态不允许解析')
            now = TimezoneUtil.utc_now()
            audit = dict(create_by=job.create_by, update_by=job.create_by, create_time=now, update_time=now)
            await Dao.add_rows(db, [dict(import_job_id=identity, row_no=row.row_no,
                source_locator=row.source_locator, candidate=row.candidate, issues=row.issues,
                state='2' if row.issues else '0', error_code=row.issues[0]['code'] if row.issues else None,
                **audit) for row in clean])
            invalid = sum(bool(row.issues) for row in clean)
            errors = [{'rowNo': row.row_no, **issue} for row in clean for issue in row.issues][:100]
            job.validation_report = dict(projectName=job.validation_report.get('projectName', ''),
                                         total=len(clean), valid=len(clean)-invalid, invalid=invalid,
                                         errors=errors, parseHash=digest)
            job.status, job.revision = '1', job.revision + 1
            job.update_by, job.update_time = job.create_by, now
            await db.commit()
            return True
        except Exception:
            await db.rollback()
            raise
