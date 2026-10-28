"""元素文档导入批次与逐行复核候选，不自动创建正式元素。"""
from alembic import op

revision = '20261028_66'
down_revision = '20261028_65'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE hf_import_job (
        import_id bigserial PRIMARY KEY, project_id bigint NOT NULL, actor_id bigint NOT NULL,
        source_file_id bigint NOT NULL, schema_version integer NOT NULL,
        source_format varchar(16) NOT NULL, include_project_name char(1) NOT NULL DEFAULT 'Y',
        parser_version varchar(100) NOT NULL, status char(1) NOT NULL DEFAULT '0',
        idempotency_key varchar(128) NOT NULL, validation_report jsonb NOT NULL DEFAULT '{}'::jsonb,
        revision bigint NOT NULL DEFAULT 1,
        create_by varchar(64) NOT NULL DEFAULT '', update_by varchar(64) NOT NULL DEFAULT '',
        create_time timestamptz(3) NOT NULL, update_time timestamptz(3) NOT NULL,
        CONSTRAINT uq_hf_import_request UNIQUE(project_id,actor_id,idempotency_key),
        CONSTRAINT ck_hf_import_job CHECK(project_id>0 AND actor_id>0 AND source_file_id>0
            AND schema_version>0 AND revision>0 AND length(parser_version)>0 AND length(idempotency_key)>0
            AND source_format IN ('pdf','xlsx','csv','docx','txt','md')
            AND include_project_name IN ('Y','N') AND status IN ('0','1','2','3','4')
            AND jsonb_typeof(validation_report)='object'))""")
    op.execute("CREATE INDEX ix_hf_import_project ON hf_import_job(project_id,create_time,import_id)")
    op.execute("CREATE INDEX ix_hf_import_pending ON hf_import_job(status,update_time,import_id)")
    op.execute("""CREATE TABLE hf_import_row (
        row_id bigserial PRIMARY KEY, import_job_id bigint NOT NULL, row_no integer NOT NULL,
        source_locator jsonb NOT NULL DEFAULT '{}'::jsonb, candidate jsonb NOT NULL DEFAULT '{}'::jsonb,
        is_selected char(1) NOT NULL DEFAULT 'Y', revision bigint NOT NULL DEFAULT 1,
        element_id bigint, state char(1) NOT NULL DEFAULT '0', error_code varchar(100),
        issues jsonb NOT NULL DEFAULT '[]'::jsonb,
        create_by varchar(64) NOT NULL DEFAULT '', update_by varchar(64) NOT NULL DEFAULT '',
        create_time timestamptz(3) NOT NULL, update_time timestamptz(3) NOT NULL,
        CONSTRAINT uq_hf_import_row UNIQUE(import_job_id,row_no),
        CONSTRAINT ck_hf_import_row CHECK(import_job_id>0 AND row_no>0 AND revision>0
            AND is_selected IN ('Y','N') AND state IN ('0','1','2')
            AND jsonb_typeof(source_locator)='object' AND jsonb_typeof(candidate)='object'
            AND jsonb_typeof(issues)='array' AND jsonb_array_length(issues)<=32),
        CONSTRAINT ck_hf_import_result CHECK(
            (state='1' AND element_id IS NOT NULL AND element_id>0 AND is_selected='Y' AND error_code IS NULL)
            OR (state IN ('0','2') AND element_id IS NULL)))""")
    comments = {
        'hf_import_job': ('剧本与表格导入复核任务', {
            'import_id': '导入批次ID', 'project_id': '目标项目ID', 'actor_id': '导入操作者ID',
            'source_file_id': '持久来源文件ID', 'schema_version': '候选结构版本',
            'source_format': '已验证的来源格式', 'include_project_name': '建议别名是否包含项目名',
            'parser_version': '解析器或受控模型配置版本', 'status': '0已上传1已校验2已确认3已完成4失败',
            'idempotency_key': '创建路径与幂等键组合摘要', 'validation_report': '校验汇总与有界错误摘要',
            'revision': '批次并发修订版本',
        }),
        'hf_import_row': ('元素导入逐行复核候选与确认结果', {
            'row_id': '导入行ID', 'import_job_id': '所属导入批次ID', 'row_no': '候选顺序号',
            'source_locator': '原始页码段落或表格行定位', 'candidate': '待复核元素字段及结构版本',
            'is_selected': '是否选中待确认', 'revision': '候选并发修订版本',
            'element_id': '确认成功创建的元素ID', 'state': '0待处理1成功2失败', 'error_code': '稳定错误代码',
            'issues': '本行有界字段诊断，不包含原始异常正文',
        }),
    }
    for table, (description, fields) in comments.items():
        op.execute(f"COMMENT ON TABLE {table} IS '{description}'")
        for name, comment in (fields | {'create_by': '创建者', 'update_by': '更新者',
                                       'create_time': '创建时间', 'update_time': '更新时间'}).items():
            op.execute(f"COMMENT ON COLUMN {table}.{name} IS '{comment}'")
    op.execute("""INSERT INTO sys_menu
        (menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time)
        SELECT '导入项目元素',menu_id,5,'','F','1','0','element:import','migration_hf_66',CURRENT_TIMESTAMP
        FROM sys_menu WHERE path='studio-project-permissions'
        AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms='element:import')""")


def downgrade():
    raise RuntimeError('导入来源和确认历史不得自动删除')
