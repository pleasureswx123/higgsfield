"""导入文件与人工候选复核记录，不提供删除入口。"""
from sqlalchemy import BigInteger, CHAR, CheckConstraint, Column, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from module_higgsfield.entity.do.asset_do import ContentRecord


class HfImportJob(ContentRecord):
    __tablename__ = 'hf_import_job'
    __table_args__ = (
        UniqueConstraint('project_id', 'actor_id', 'idempotency_key', name='uq_hf_import_request'),
        CheckConstraint("project_id>0 AND actor_id>0 AND source_file_id>0 AND schema_version>0 AND revision>0 "
            "AND length(parser_version)>0 AND length(idempotency_key)>0 "
            "AND source_format IN ('pdf','xlsx','csv','docx','txt','md') AND include_project_name IN ('Y','N') "
            "AND status IN ('0','1','2','3','4') AND jsonb_typeof(validation_report)='object'", name='ck_hf_import_job'),
        Index('ix_hf_import_project', 'project_id', 'create_time', 'import_id'),
        Index('ix_hf_import_pending', 'status', 'update_time', 'import_id'),
        {'comment': '剧本与表格导入复核任务', 'info': {'migration_managed': True}},
    )
    import_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='导入批次ID')
    project_id = Column(BigInteger, nullable=False, comment='目标项目ID')
    actor_id = Column(BigInteger, nullable=False, comment='导入操作者ID')
    source_file_id = Column(BigInteger, nullable=False, comment='持久来源文件ID')
    schema_version = Column(Integer, nullable=False, comment='候选结构版本')
    source_format = Column(String(16), nullable=False, comment='已验证的来源格式')
    include_project_name = Column(CHAR(1), nullable=False, server_default='Y', comment='建议别名是否包含项目名')
    parser_version = Column(String(100), nullable=False, comment='解析器或受控模型配置版本')
    status = Column(CHAR(1), nullable=False, server_default='0', comment='0已上传1已校验2已确认3已完成4失败')
    idempotency_key = Column(String(128), nullable=False, comment='创建路径与幂等键组合摘要')
    validation_report = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), comment='校验汇总与有界错误摘要')
    revision = Column(BigInteger, nullable=False, server_default='1', comment='批次并发修订版本')


class HfImportRow(ContentRecord):
    __tablename__ = 'hf_import_row'
    __table_args__ = (
        UniqueConstraint('import_job_id', 'row_no', name='uq_hf_import_row'),
        CheckConstraint("import_job_id>0 AND row_no>0 AND revision>0 AND is_selected IN ('Y','N') "
            "AND state IN ('0','1','2') AND jsonb_typeof(source_locator)='object' "
            "AND jsonb_typeof(candidate)='object' AND jsonb_typeof(issues)='array' "
            "AND jsonb_array_length(issues)<=32", name='ck_hf_import_row'),
        CheckConstraint("(state='1' AND element_id IS NOT NULL AND element_id>0 AND is_selected='Y' AND error_code IS NULL) "
            "OR (state IN ('0','2') AND element_id IS NULL)", name='ck_hf_import_result'),
        {'comment': '元素导入逐行复核候选与确认结果', 'info': {'migration_managed': True}},
    )
    row_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='导入行ID')
    import_job_id = Column(BigInteger, nullable=False, comment='所属导入批次ID')
    row_no = Column(Integer, nullable=False, comment='候选顺序号')
    source_locator = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), comment='原始页码段落或表格行定位')
    candidate = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"), comment='待复核元素字段及结构版本')
    is_selected = Column(CHAR(1), nullable=False, server_default='Y', comment='是否选中待确认')
    revision = Column(BigInteger, nullable=False, server_default='1', comment='候选并发修订版本')
    element_id = Column(BigInteger, comment='确认成功创建的元素ID')
    state = Column(CHAR(1), nullable=False, server_default='0', comment='0待处理1成功2失败')
    error_code = Column(String(100), comment='稳定错误代码')
    issues = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"), comment='本行有界字段诊断，不包含原始异常正文')
