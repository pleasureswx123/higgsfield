"""上传、持久媒体和素材不可变版本真实迁移。"""

from alembic import op
from sqlalchemy import text

revision = '20261027_06'
down_revision = '20261027_05'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE hf_upload_session (\n\tupload_id BIGSERIAL NOT NULL, \n\towner_id BIGINT NOT NULL, \n\tproject_id BIGINT, \n\tpurpose VARCHAR(32) NOT NULL, \n\tfile_name VARCHAR(255) NOT NULL, \n\tdeclared_mime_type VARCHAR(255) NOT NULL, \n\tbyte_size BIGINT NOT NULL, \n\tpart_size BIGINT NOT NULL, \n\tpart_count INTEGER NOT NULL, \n\texpected_sha256 CHAR(64), \n\tverified_sha256 CHAR(64), \n\tstate CHAR(1) DEFAULT '0' NOT NULL, \n\texpires_time TIMESTAMP WITH TIME ZONE NOT NULL, \n\tcompleted_file_id BIGINT, \n\tvalidation_errors JSONB DEFAULT '[]'::jsonb NOT NULL, \n\tschema_version INTEGER DEFAULT '1' NOT NULL, \n\trevision BIGINT DEFAULT '1' NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (upload_id), \n\tCONSTRAINT ck_hf_upload_sizes CHECK (byte_size > 0 AND part_size > 0 AND part_count > 0), \n\tCONSTRAINT ck_hf_upload_state CHECK (state IN ('0','1','2','3','4','5','6')), \n\tCONSTRAINT ck_hf_upload_purpose CHECK ((purpose IN ('asset','element_import') AND project_id IS NOT NULL) OR (purpose IN ('price_source','reconciliation') AND project_id IS NULL)), \n\tCONSTRAINT ck_hf_upload_expiry CHECK (expires_time > create_time AND revision > 0), \n\tCONSTRAINT ck_hf_upload_ready CHECK (state != '3' OR (completed_file_id IS NOT NULL AND verified_sha256 IS NOT NULL AND expected_sha256 IS NOT NULL AND verified_sha256=expected_sha256))\n)"
    )
    op.execute('CREATE INDEX ix_hf_upload_expiry ON hf_upload_session (state, expires_time)')
    op.execute('CREATE INDEX ix_hf_upload_owner ON hf_upload_session (owner_id, project_id, create_time, upload_id)')
    op.execute("COMMENT ON TABLE hf_upload_session IS '平台上传会话'")
    op.execute("COMMENT ON COLUMN hf_upload_session.upload_id IS '上传会话ID'")
    op.execute("COMMENT ON COLUMN hf_upload_session.owner_id IS '上传所有者ID'")
    op.execute("COMMENT ON COLUMN hf_upload_session.project_id IS '所属项目ID'")
    op.execute("COMMENT ON COLUMN hf_upload_session.purpose IS '上传用途'")
    op.execute("COMMENT ON COLUMN hf_upload_session.file_name IS '展示文件名，不作为存储路径'")
    op.execute("COMMENT ON COLUMN hf_upload_session.declared_mime_type IS '客户端声明类型'")
    op.execute("COMMENT ON COLUMN hf_upload_session.byte_size IS '声明总字节数'")
    op.execute("COMMENT ON COLUMN hf_upload_session.part_size IS '固定分片大小'")
    op.execute("COMMENT ON COLUMN hf_upload_session.part_count IS '分片数量'")
    op.execute("COMMENT ON COLUMN hf_upload_session.expected_sha256 IS '期望整文件摘要'")
    op.execute("COMMENT ON COLUMN hf_upload_session.verified_sha256 IS '实际整文件摘要'")
    op.execute("COMMENT ON COLUMN hf_upload_session.state IS '0创建1上传2校验3就绪4失败5取消6过期'")
    op.execute("COMMENT ON COLUMN hf_upload_session.expires_time IS '未绑定上传有效期'")
    op.execute("COMMENT ON COLUMN hf_upload_session.completed_file_id IS '验证完成的文件ID'")
    op.execute("COMMENT ON COLUMN hf_upload_session.validation_errors IS '白名单校验错误'")
    op.execute("COMMENT ON COLUMN hf_upload_session.schema_version IS '错误信息格式版本'")
    op.execute("COMMENT ON COLUMN hf_upload_session.revision IS '内部并发修订'")
    op.execute("COMMENT ON COLUMN hf_upload_session.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_upload_session.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_upload_session.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_upload_session.update_time IS '更新时间'")
    op.execute(
        "CREATE TABLE hf_upload_part (\n\tpart_id BIGSERIAL NOT NULL, \n\tsession_id BIGINT NOT NULL, \n\tpart_no INTEGER NOT NULL, \n\tbyte_offset BIGINT NOT NULL, \n\tbyte_size BIGINT NOT NULL, \n\tsha256 CHAR(64) NOT NULL, \n\tstorage_key TEXT NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (part_id), \n\tCONSTRAINT uq_hf_upload_part UNIQUE (session_id, part_no), \n\tCONSTRAINT ck_hf_upload_part_size CHECK (part_no > 0 AND byte_offset >= 0 AND byte_size > 0)\n)"
    )
    op.execute("COMMENT ON TABLE hf_upload_part IS '上传已接收分片'")
    op.execute("COMMENT ON COLUMN hf_upload_part.part_id IS '分片ID'")
    op.execute("COMMENT ON COLUMN hf_upload_part.session_id IS '上传会话ID'")
    op.execute("COMMENT ON COLUMN hf_upload_part.part_no IS '一开始的分片编号'")
    op.execute("COMMENT ON COLUMN hf_upload_part.byte_offset IS '零起点字节偏移'")
    op.execute("COMMENT ON COLUMN hf_upload_part.byte_size IS '分片实际字节数'")
    op.execute("COMMENT ON COLUMN hf_upload_part.sha256 IS '分片实际摘要'")
    op.execute("COMMENT ON COLUMN hf_upload_part.storage_key IS '内部暂存定位键'")
    op.execute("COMMENT ON COLUMN hf_upload_part.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_upload_part.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_upload_part.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_upload_part.update_time IS '更新时间'")
    op.execute(
        "CREATE TABLE hf_stored_file (\n\tfile_id BIGSERIAL NOT NULL, \n\tstorage_key TEXT NOT NULL, \n\tsha256 CHAR(64) NOT NULL, \n\tbyte_size BIGINT NOT NULL, \n\tmime_type VARCHAR(100) NOT NULL, \n\twidth INTEGER, \n\theight INTEGER, \n\tseconds NUMERIC(18, 6), \n\tstate CHAR(1) NOT NULL, \n\tpurged_time TIMESTAMP WITH TIME ZONE, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (file_id), \n\tCONSTRAINT uq_hf_stored_file_key UNIQUE (storage_key), \n\tCONSTRAINT ck_hf_stored_file_sizes CHECK (byte_size >= 0 AND (width IS NULL OR width > 0) AND (height IS NULL OR height > 0) AND (seconds IS NULL OR seconds > 0)), \n\tCONSTRAINT ck_hf_stored_file_state CHECK (state IN ('0','1','2','3','4'))\n)"
    )
    op.execute('CREATE INDEX ix_hf_stored_file_hash ON hf_stored_file (sha256, byte_size)')
    op.execute("COMMENT ON TABLE hf_stored_file IS '受控持久文件'")
    op.execute("COMMENT ON COLUMN hf_stored_file.file_id IS '文件ID'")
    op.execute("COMMENT ON COLUMN hf_stored_file.storage_key IS '服务端生成相对存储键'")
    op.execute("COMMENT ON COLUMN hf_stored_file.sha256 IS '文件内容摘要'")
    op.execute("COMMENT ON COLUMN hf_stored_file.byte_size IS '文件字节数'")
    op.execute("COMMENT ON COLUMN hf_stored_file.mime_type IS '经校验实际类型'")
    op.execute("COMMENT ON COLUMN hf_stored_file.width IS '媒体宽度'")
    op.execute("COMMENT ON COLUMN hf_stored_file.height IS '媒体高度'")
    op.execute("COMMENT ON COLUMN hf_stored_file.seconds IS '视频时长秒'")
    op.execute("COMMENT ON COLUMN hf_stored_file.state IS '0暂存1就绪2隔离3丢失4已清理'")
    op.execute("COMMENT ON COLUMN hf_stored_file.purged_time IS '物理清理时间证据'")
    op.execute("COMMENT ON COLUMN hf_stored_file.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_stored_file.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_stored_file.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_stored_file.update_time IS '更新时间'")
    op.execute(
        "CREATE TABLE hf_asset (\n\tasset_id BIGSERIAL NOT NULL, \n\tspace_id BIGINT NOT NULL, \n\tasset_name VARCHAR(200) NOT NULL, \n\tmedia_type VARCHAR(32) NOT NULL, \n\tcreate_user_id BIGINT NOT NULL, \n\tcurrent_version_id BIGINT, \n\trevision BIGINT DEFAULT '1' NOT NULL, \n\tdel_flag CHAR(1) DEFAULT '0' NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (asset_id), \n\tCONSTRAINT uq_hf_asset_space_identity UNIQUE (asset_id, space_id), \n\tCONSTRAINT ck_hf_asset_revision CHECK (revision > 0), \n\tCONSTRAINT ck_hf_asset_del CHECK (del_flag IN ('0','2')), \n\tCONSTRAINT ck_hf_asset_media_type CHECK (media_type IN ('image','video','audio','document'))\n)"
    )
    op.execute("CREATE INDEX ix_hf_asset_space_time ON hf_asset (space_id, create_time, asset_id) WHERE del_flag='0'")
    op.execute("COMMENT ON TABLE hf_asset IS '素材身份'")
    op.execute("COMMENT ON COLUMN hf_asset.asset_id IS '素材ID'")
    op.execute("COMMENT ON COLUMN hf_asset.space_id IS '归属空间ID'")
    op.execute("COMMENT ON COLUMN hf_asset.asset_name IS '素材名称'")
    op.execute("COMMENT ON COLUMN hf_asset.media_type IS '素材媒体类型'")
    op.execute("COMMENT ON COLUMN hf_asset.create_user_id IS '作者用户ID'")
    op.execute("COMMENT ON COLUMN hf_asset.current_version_id IS '当前就绪版本ID'")
    op.execute("COMMENT ON COLUMN hf_asset.revision IS '并发修订'")
    op.execute("COMMENT ON COLUMN hf_asset.del_flag IS '0存在2删除'")
    op.execute("COMMENT ON COLUMN hf_asset.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_asset.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_asset.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_asset.update_time IS '更新时间'")
    op.execute(
        "CREATE TABLE hf_asset_version (\n\tversion_id BIGSERIAL NOT NULL, \n\tasset_id BIGINT NOT NULL, \n\tversion_no INTEGER NOT NULL, \n\tfile_id BIGINT NOT NULL, \n\tsource_output_id BIGINT, \n\tcreate_user_id BIGINT NOT NULL, \n\tmetadata JSONB DEFAULT '{}'::jsonb NOT NULL, \n\tsource_asset_version_id BIGINT, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (version_id), \n\tCONSTRAINT uq_hf_asset_version_no UNIQUE (asset_id, version_no), \n\tCONSTRAINT uq_hf_asset_version_identity UNIQUE (asset_id, version_id), \n\tCONSTRAINT ck_hf_asset_version_no CHECK (version_no > 0), \n\tCONSTRAINT ck_hf_asset_source_self CHECK (source_asset_version_id IS NULL OR source_asset_version_id <> version_id), \n\tCONSTRAINT ck_hf_asset_source_one CHECK (num_nonnulls(source_asset_version_id,source_output_id) <= 1)\n)"
    )
    op.execute("COMMENT ON TABLE hf_asset_version IS '素材不可变版本'")
    op.execute("COMMENT ON COLUMN hf_asset_version.version_id IS '素材版本ID'")
    op.execute("COMMENT ON COLUMN hf_asset_version.asset_id IS '所属素材ID'")
    op.execute("COMMENT ON COLUMN hf_asset_version.version_no IS '递增版本号'")
    op.execute("COMMENT ON COLUMN hf_asset_version.file_id IS '持久文件ID'")
    op.execute("COMMENT ON COLUMN hf_asset_version.source_output_id IS '来源生成作品ID'")
    op.execute("COMMENT ON COLUMN hf_asset_version.create_user_id IS '版本创建者ID'")
    op.execute("COMMENT ON COLUMN hf_asset_version.metadata IS '媒体分析快照'")
    op.execute("COMMENT ON COLUMN hf_asset_version.source_asset_version_id IS '固定来源素材版本ID'")
    op.execute("COMMENT ON COLUMN hf_asset_version.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_asset_version.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_asset_version.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_asset_version.update_time IS '更新时间'")
    op.execute(
        "CREATE TABLE hf_upload_binding (\n\tbinding_id BIGSERIAL NOT NULL, \n\tsession_id BIGINT NOT NULL, \n\tasset_version_id BIGINT, \n\tprice_source_id BIGINT, \n\treconciliation_batch_id BIGINT, \n\timport_job_id BIGINT, \n\tbound_by BIGINT NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (binding_id), \n\tCONSTRAINT uq_hf_upload_binding_session UNIQUE (session_id), \n\tCONSTRAINT ck_hf_upload_binding_target CHECK (num_nonnulls(asset_version_id,price_source_id,reconciliation_batch_id,import_job_id)=1)\n)"
    )
    op.execute(
        'CREATE UNIQUE INDEX uq_hf_upload_binding_asset_version_id ON hf_upload_binding (asset_version_id) WHERE asset_version_id IS NOT NULL'
    )
    op.execute(
        'CREATE UNIQUE INDEX uq_hf_upload_binding_import_job_id ON hf_upload_binding (import_job_id) WHERE import_job_id IS NOT NULL'
    )
    op.execute(
        'CREATE UNIQUE INDEX uq_hf_upload_binding_price_source_id ON hf_upload_binding (price_source_id) WHERE price_source_id IS NOT NULL'
    )
    op.execute(
        'CREATE UNIQUE INDEX uq_hf_upload_binding_reconciliation_batch_id ON hf_upload_binding (reconciliation_batch_id) WHERE reconciliation_batch_id IS NOT NULL'
    )
    op.execute("COMMENT ON TABLE hf_upload_binding IS '上传完成结果唯一业务绑定'")
    op.execute("COMMENT ON COLUMN hf_upload_binding.binding_id IS '绑定ID'")
    op.execute("COMMENT ON COLUMN hf_upload_binding.session_id IS '上传会话ID'")
    op.execute("COMMENT ON COLUMN hf_upload_binding.asset_version_id IS '素材版本ID'")
    op.execute("COMMENT ON COLUMN hf_upload_binding.price_source_id IS '价格证据ID'")
    op.execute("COMMENT ON COLUMN hf_upload_binding.reconciliation_batch_id IS '对账批次ID'")
    op.execute("COMMENT ON COLUMN hf_upload_binding.import_job_id IS '导入任务ID'")
    op.execute("COMMENT ON COLUMN hf_upload_binding.bound_by IS '执行绑定的上传所有者ID'")
    op.execute("COMMENT ON COLUMN hf_upload_binding.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_upload_binding.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_upload_binding.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_upload_binding.update_time IS '更新时间'")
    op.execute(
        "CREATE TABLE hf_folder_entry (\n\tentry_id BIGSERIAL NOT NULL, \n\tspace_id BIGINT NOT NULL, \n\tfolder_id BIGINT, \n\tasset_id BIGINT, \n\toutput_id BIGINT, \n\tproject_asset_ref_id BIGINT, \n\torder_num INTEGER DEFAULT '0' NOT NULL, \n\trevision BIGINT DEFAULT '1' NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (entry_id), \n\tCONSTRAINT ck_hf_folder_entry_target CHECK (num_nonnulls(asset_id,output_id,project_asset_ref_id)=1), \n\tCONSTRAINT ck_hf_folder_entry_revision CHECK (revision > 0)\n)"
    )
    op.execute('CREATE INDEX ix_hf_folder_entry_folder ON hf_folder_entry (space_id, folder_id)')
    op.execute(
        'CREATE UNIQUE INDEX uq_hf_folder_entry_asset_id ON hf_folder_entry (space_id, asset_id) WHERE asset_id IS NOT NULL'
    )
    op.execute(
        'CREATE UNIQUE INDEX uq_hf_folder_entry_output_id ON hf_folder_entry (space_id, output_id) WHERE output_id IS NOT NULL'
    )
    op.execute(
        'CREATE UNIQUE INDEX uq_hf_folder_entry_project_asset_ref_id ON hf_folder_entry (space_id, project_asset_ref_id) WHERE project_asset_ref_id IS NOT NULL'
    )
    op.execute("COMMENT ON TABLE hf_folder_entry IS '素材主目录归属'")
    op.execute("COMMENT ON COLUMN hf_folder_entry.entry_id IS '目录归属ID'")
    op.execute("COMMENT ON COLUMN hf_folder_entry.space_id IS '展示空间ID'")
    op.execute("COMMENT ON COLUMN hf_folder_entry.folder_id IS '当前目录ID，空表示根层'")
    op.execute("COMMENT ON COLUMN hf_folder_entry.asset_id IS '本空间素材ID'")
    op.execute("COMMENT ON COLUMN hf_folder_entry.output_id IS '项目生成作品ID'")
    op.execute("COMMENT ON COLUMN hf_folder_entry.project_asset_ref_id IS '跨项目引用ID'")
    op.execute("COMMENT ON COLUMN hf_folder_entry.order_num IS '目录内顺序'")
    op.execute("COMMENT ON COLUMN hf_folder_entry.revision IS '归属并发修订'")
    op.execute("COMMENT ON COLUMN hf_folder_entry.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_folder_entry.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_folder_entry.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_folder_entry.update_time IS '更新时间'")
    for label, permission in [
        ('上传项目素材', 'asset:upload'),
        ('创建项目素材', 'asset:create'),
        ('编辑项目素材', 'asset:edit'),
        ('下载项目素材', 'asset:download'),
    ]:
        op.execute(
            text("""INSERT INTO sys_menu
        (menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time)
        SELECT :label,menu_id,4,'','F','1','0',:permission,'migration_hf_06',CURRENT_TIMESTAMP
        FROM sys_menu WHERE path='studio-project-permissions'
        AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms=:permission)""").bindparams(
                label=label, permission=permission
            )
        )


def downgrade():
    raise RuntimeError('上传和素材证据不允许自动回退删除')
