"""创建目录和回收证据；冻结DDL，不依赖运行期模型。"""

from alembic import op
from sqlalchemy import text

revision = '20261027_04'
down_revision = '20261027_03'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "\nCREATE TABLE hf_folder (\n\tfolder_id BIGSERIAL NOT NULL, \n\tspace_id BIGINT NOT NULL, \n\tparent_id BIGINT, \n\tfolder_name VARCHAR(200) NOT NULL, \n\tnormalized_name VARCHAR(200) NOT NULL, \n\tdescription TEXT DEFAULT '' NOT NULL, \n\tcolor VARCHAR(16) DEFAULT 'lime' NOT NULL, \n\tfolder_kind VARCHAR(16) DEFAULT 'media' NOT NULL, \n\torder_num INTEGER DEFAULT '0' NOT NULL, \n\trevision BIGINT DEFAULT '1' NOT NULL, \n\tdel_flag CHAR(1) DEFAULT '0' NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (folder_id), \n\tCONSTRAINT uq_hf_folder_space UNIQUE (folder_id, space_id), \n\tCONSTRAINT ck_hf_folder_parent CHECK (parent_id <> folder_id), \n\tCONSTRAINT ck_hf_folder_revision CHECK (revision > 0), \n\tCONSTRAINT ck_hf_folder_del CHECK (del_flag IN ('0','2')), \n\tCONSTRAINT ck_hf_folder_kind CHECK (folder_kind IN ('media','element')), \n\tCONSTRAINT ck_hf_folder_color CHECK (color IN ('lime','cyan','slate','violet','purple','pink','yellow'))\n)\n\n"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_hf_folder_child ON hf_folder (space_id, parent_id, normalized_name) WHERE parent_id IS NOT NULL AND del_flag='0'"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_hf_folder_root ON hf_folder (space_id, normalized_name) WHERE parent_id IS NULL AND del_flag='0'"
    )
    op.execute("COMMENT ON TABLE hf_folder IS '空间目录'")
    op.execute("COMMENT ON COLUMN hf_folder.folder_id IS '目录ID'")
    op.execute("COMMENT ON COLUMN hf_folder.space_id IS '归属空间ID'")
    op.execute("COMMENT ON COLUMN hf_folder.parent_id IS '父目录ID，空表示根目录'")
    op.execute("COMMENT ON COLUMN hf_folder.folder_name IS '目录显示名称'")
    op.execute("COMMENT ON COLUMN hf_folder.normalized_name IS 'NFKC规范化并忽略大小写的名称'")
    op.execute("COMMENT ON COLUMN hf_folder.description IS '目录描述'")
    op.execute("COMMENT ON COLUMN hf_folder.color IS '目录颜色'")
    op.execute("COMMENT ON COLUMN hf_folder.folder_kind IS '目录类型'")
    op.execute("COMMENT ON COLUMN hf_folder.order_num IS '显示顺序'")
    op.execute("COMMENT ON COLUMN hf_folder.revision IS '并发版本'")
    op.execute("COMMENT ON COLUMN hf_folder.del_flag IS '删除标志：0存在2删除'")
    op.execute("COMMENT ON COLUMN hf_folder.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_folder.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_folder.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_folder.update_time IS '更新时间'")
    op.execute(
        "\nCREATE TABLE hf_recycle_entry (\n\trecycle_id BIGSERIAL NOT NULL, \n\tproject_id BIGINT NOT NULL, \n\ttarget_kind VARCHAR(16) NOT NULL, \n\ttarget_id BIGINT NOT NULL, \n\toriginal_parent_id BIGINT, \n\tdeleted_time TIMESTAMP WITH TIME ZONE NOT NULL, \n\trestore_until TIMESTAMP WITH TIME ZONE NOT NULL, \n\tactor_id BIGINT NOT NULL, \n\tstate VARCHAR(16) DEFAULT 'active' NOT NULL, \n\trestored_time TIMESTAMP WITH TIME ZONE, \n\trestored_by BIGINT, \n\trevision BIGINT DEFAULT '1' NOT NULL, \n\tsnapshot JSONB DEFAULT '{}'::jsonb NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (recycle_id), \n\tCONSTRAINT ck_hf_recycle_kind CHECK (target_kind IN ('folder','element','asset','output')), \n\tCONSTRAINT ck_hf_recycle_state CHECK (state IN ('active','restored','expired')), \n\tCONSTRAINT ck_hf_recycle_window CHECK (restore_until > deleted_time), \n\tCONSTRAINT ck_hf_recycle_revision CHECK (revision > 0)\n)\n\n"
    )
    op.execute('CREATE INDEX ix_hf_recycle_project ON hf_recycle_entry (project_id, state, deleted_time, recycle_id)')
    op.execute(
        "CREATE UNIQUE INDEX uq_hf_recycle_active ON hf_recycle_entry (target_kind, target_id) WHERE state='active'"
    )
    op.execute("COMMENT ON TABLE hf_recycle_entry IS '内容回收记录'")
    op.execute("COMMENT ON COLUMN hf_recycle_entry.recycle_id IS '回收记录ID'")
    op.execute("COMMENT ON COLUMN hf_recycle_entry.project_id IS '所属项目ID'")
    op.execute("COMMENT ON COLUMN hf_recycle_entry.target_kind IS '对象类型'")
    op.execute("COMMENT ON COLUMN hf_recycle_entry.target_id IS '对象稳定ID'")
    op.execute("COMMENT ON COLUMN hf_recycle_entry.original_parent_id IS '原父目录ID'")
    op.execute("COMMENT ON COLUMN hf_recycle_entry.deleted_time IS '删除时间'")
    op.execute("COMMENT ON COLUMN hf_recycle_entry.restore_until IS '自助恢复截止时间'")
    op.execute("COMMENT ON COLUMN hf_recycle_entry.actor_id IS '删除操作者ID'")
    op.execute("COMMENT ON COLUMN hf_recycle_entry.state IS '回收状态'")
    op.execute("COMMENT ON COLUMN hf_recycle_entry.restored_time IS '恢复时间'")
    op.execute("COMMENT ON COLUMN hf_recycle_entry.restored_by IS '恢复操作者ID'")
    op.execute("COMMENT ON COLUMN hf_recycle_entry.revision IS '并发版本'")
    op.execute("COMMENT ON COLUMN hf_recycle_entry.snapshot IS '删除前展示快照'")
    op.execute("COMMENT ON COLUMN hf_recycle_entry.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_recycle_entry.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_recycle_entry.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_recycle_entry.update_time IS '更新时间'")
    for label, permission in [('查看项目素材', 'asset:read'), ('管理项目目录', 'folder:write')]:
        op.execute(
            text("""INSERT INTO sys_menu
            (menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time)
            SELECT :label,menu_id,3,'','F','1','0',:permission,'migration_hf_04',CURRENT_TIMESTAMP
            FROM sys_menu WHERE path='studio-project-permissions'
            AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms=:permission)""").bindparams(
                label=label, permission=permission
            )
        )


def downgrade():
    raise RuntimeError('目录和回收证据回退需单独审核迁移')
