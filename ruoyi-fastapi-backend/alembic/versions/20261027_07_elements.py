"""元素身份、不可变修订与版本化属性定义。"""

from alembic import op
from sqlalchemy import text

revision = '20261027_07'
down_revision = '20261027_06'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE hf_element (\n\telement_id BIGSERIAL NOT NULL, \n\tspace_id BIGINT NOT NULL, \n\telement_name VARCHAR(200) NOT NULL, \n\talias VARCHAR(100) NOT NULL, \n\tcategory VARCHAR(32) NOT NULL, \n\tcreate_user_id BIGINT NOT NULL, \n\tcurrent_revision_id BIGINT, \n\tperformer_id BIGINT, \n\tfolder_id BIGINT, \n\twork_status CHAR(1) DEFAULT '0' NOT NULL, \n\trevision BIGINT DEFAULT '1' NOT NULL, \n\tdel_flag CHAR(1) DEFAULT '0' NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (element_id), \n\tCONSTRAINT uq_hf_element_alias UNIQUE (space_id, alias), \n\tCONSTRAINT ck_hf_element_category CHECK (category IN ('character','scene','prop','other')), \n\tCONSTRAINT ck_hf_element_status CHECK (work_status IN ('0','1','2','3','4')), \n\tCONSTRAINT ck_hf_element_lifecycle CHECK (del_flag IN ('0','2') AND revision > 0)\n)"
    )
    op.execute(
        "CREATE INDEX ix_hf_element_space ON hf_element (space_id, category, create_time, element_id) WHERE del_flag='0'"
    )
    op.execute("COMMENT ON TABLE hf_element IS '元素身份与当前修订指针'")
    op.execute("COMMENT ON COLUMN hf_element.element_id IS '元素ID'")
    op.execute("COMMENT ON COLUMN hf_element.space_id IS '所属空间ID'")
    op.execute("COMMENT ON COLUMN hf_element.element_name IS '元素展示名称'")
    op.execute("COMMENT ON COLUMN hf_element.alias IS '空间内唯一业务别名，删除后保留'")
    op.execute("COMMENT ON COLUMN hf_element.category IS '分类：角色场景道具其他'")
    op.execute("COMMENT ON COLUMN hf_element.create_user_id IS '创建用户ID'")
    op.execute("COMMENT ON COLUMN hf_element.current_revision_id IS '当前不可变修订ID'")
    op.execute("COMMENT ON COLUMN hf_element.performer_id IS '负责人的有效项目成员用户ID'")
    op.execute("COMMENT ON COLUMN hf_element.folder_id IS '同空间元素目录ID，空为根目录'")
    op.execute("COMMENT ON COLUMN hf_element.work_status IS '0未开始1制作中2待审3通过4驳回'")
    op.execute("COMMENT ON COLUMN hf_element.revision IS '身份并发版本'")
    op.execute("COMMENT ON COLUMN hf_element.del_flag IS '删除标志：0存在2删除'")
    op.execute("COMMENT ON COLUMN hf_element.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_element.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_element.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_element.update_time IS '更新时间'")
    op.execute(
        "CREATE TABLE hf_element_revision (\n\trevision_id BIGSERIAL NOT NULL, \n\telement_id BIGINT NOT NULL, \n\trevision_no INTEGER NOT NULL, \n\tdescription TEXT DEFAULT '' NOT NULL, \n\tproperty_snapshot JSONB DEFAULT '[]'::jsonb NOT NULL, \n\tcreate_user_id BIGINT NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (revision_id), \n\tCONSTRAINT uq_hf_element_revision_no UNIQUE (element_id, revision_no), \n\tCONSTRAINT uq_hf_element_revision_identity UNIQUE (element_id, revision_id), \n\tCONSTRAINT ck_hf_element_revision_no CHECK (revision_no > 0), \n\tCONSTRAINT ck_hf_element_property_snapshot CHECK (jsonb_typeof(property_snapshot)='array')\n)"
    )
    op.execute("COMMENT ON TABLE hf_element_revision IS '元素不可变生成资料修订'")
    op.execute("COMMENT ON COLUMN hf_element_revision.revision_id IS '修订ID'")
    op.execute("COMMENT ON COLUMN hf_element_revision.element_id IS '元素身份ID'")
    op.execute("COMMENT ON COLUMN hf_element_revision.revision_no IS '递增内部修订号'")
    op.execute("COMMENT ON COLUMN hf_element_revision.description IS '参与生成的描述'")
    op.execute("COMMENT ON COLUMN hf_element_revision.property_snapshot IS '属性定义版本和值的不可变快照'")
    op.execute("COMMENT ON COLUMN hf_element_revision.create_user_id IS '修订创建用户ID'")
    op.execute("COMMENT ON COLUMN hf_element_revision.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_element_revision.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_element_revision.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_element_revision.update_time IS '更新时间'")
    op.execute(
        "CREATE TABLE hf_element_revision_label (\n\tlabel_id BIGSERIAL NOT NULL, \n\telement_revision_id BIGINT NOT NULL, \n\tlabel VARCHAR(100) DEFAULT '' NOT NULL, \n\trevision BIGINT DEFAULT '1' NOT NULL, \n\tupdate_user_id BIGINT NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (label_id), \n\tCONSTRAINT uq_hf_element_label_revision UNIQUE (element_revision_id), \n\tCONSTRAINT ck_hf_element_label_revision CHECK (revision > 0)\n)"
    )
    op.execute("COMMENT ON TABLE hf_element_revision_label IS '元素修订展示标签，不参与生成身份'")
    op.execute("COMMENT ON COLUMN hf_element_revision_label.label_id IS '标签记录ID'")
    op.execute("COMMENT ON COLUMN hf_element_revision_label.element_revision_id IS '元素修订ID'")
    op.execute("COMMENT ON COLUMN hf_element_revision_label.label IS '用户展示标签'")
    op.execute("COMMENT ON COLUMN hf_element_revision_label.revision IS '标签并发版本'")
    op.execute("COMMENT ON COLUMN hf_element_revision_label.update_user_id IS '标签修改用户ID'")
    op.execute("COMMENT ON COLUMN hf_element_revision_label.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_element_revision_label.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_element_revision_label.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_element_revision_label.update_time IS '更新时间'")
    op.execute(
        "CREATE TABLE hf_element_revision_media (\n\tmedia_id BIGSERIAL NOT NULL, \n\telement_revision_id BIGINT NOT NULL, \n\tasset_version_id BIGINT NOT NULL, \n\tordinal INTEGER NOT NULL, \n\tis_primary CHAR(1) DEFAULT 'N' NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (media_id), \n\tCONSTRAINT uq_hf_element_media_order UNIQUE (element_revision_id, ordinal), \n\tCONSTRAINT uq_hf_element_media_asset UNIQUE (element_revision_id, asset_version_id), \n\tCONSTRAINT ck_hf_element_media_values CHECK (ordinal >= 0 AND is_primary IN ('Y','N'))\n)"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_hf_element_media_primary ON hf_element_revision_media (element_revision_id) WHERE is_primary='Y'"
    )
    op.execute("COMMENT ON TABLE hf_element_revision_media IS '元素修订固定素材多图与顺序'")
    op.execute("COMMENT ON COLUMN hf_element_revision_media.media_id IS '修订媒体ID'")
    op.execute("COMMENT ON COLUMN hf_element_revision_media.element_revision_id IS '元素修订ID'")
    op.execute("COMMENT ON COLUMN hf_element_revision_media.asset_version_id IS '固定素材版本ID'")
    op.execute("COMMENT ON COLUMN hf_element_revision_media.ordinal IS '媒体排序序号'")
    op.execute("COMMENT ON COLUMN hf_element_revision_media.is_primary IS '是否主图：Y是N否'")
    op.execute("COMMENT ON COLUMN hf_element_revision_media.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_element_revision_media.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_element_revision_media.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_element_revision_media.update_time IS '更新时间'")
    op.execute(
        "CREATE TABLE hf_property_definition (\n\tproperty_id BIGSERIAL NOT NULL, \n\tspace_id BIGINT NOT NULL, \n\tproperty_key VARCHAR(100) NOT NULL, \n\tversion_no INTEGER NOT NULL, \n\tproperty_name VARCHAR(200) NOT NULL, \n\tvalue_type VARCHAR(32) NOT NULL, \n\toptions JSONB DEFAULT '[]'::jsonb NOT NULL, \n\tcreate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tupdate_by VARCHAR(64) DEFAULT '' NOT NULL, \n\tcreate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tupdate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (property_id), \n\tCONSTRAINT uq_hf_property_version UNIQUE (space_id, property_key, version_no), \n\tCONSTRAINT ck_hf_property_version CHECK (version_no > 0), \n\tCONSTRAINT ck_hf_property_type CHECK (value_type IN ('text','single_select','multi_select')), \n\tCONSTRAINT ck_hf_property_options CHECK (jsonb_typeof(options)='array')\n)"
    )
    op.execute("COMMENT ON TABLE hf_property_definition IS '元素属性定义不可变版本'")
    op.execute("COMMENT ON COLUMN hf_property_definition.property_id IS '属性定义版本ID'")
    op.execute("COMMENT ON COLUMN hf_property_definition.space_id IS '定义所属空间ID'")
    op.execute("COMMENT ON COLUMN hf_property_definition.property_key IS '稳定属性键'")
    op.execute("COMMENT ON COLUMN hf_property_definition.version_no IS '属性定义内部版本号'")
    op.execute("COMMENT ON COLUMN hf_property_definition.property_name IS '属性显示名称'")
    op.execute("COMMENT ON COLUMN hf_property_definition.value_type IS '文本、多选或历史单选'")
    op.execute("COMMENT ON COLUMN hf_property_definition.options IS '合法选项列表'")
    op.execute("COMMENT ON COLUMN hf_property_definition.create_by IS '创建者'")
    op.execute("COMMENT ON COLUMN hf_property_definition.update_by IS '更新者'")
    op.execute("COMMENT ON COLUMN hf_property_definition.create_time IS '创建时间'")
    op.execute("COMMENT ON COLUMN hf_property_definition.update_time IS '更新时间'")
    for label, permission in [
        ('查看项目元素', 'element:read'),
        ('创建项目元素', 'element:create'),
        ('编辑项目元素', 'element:edit'),
        ('回收项目元素', 'element:remove'),
        ('复制项目元素', 'element:copy'),
        ('配置元素属性', 'element:configure'),
    ]:
        op.execute(
            text("""INSERT INTO sys_menu
            (menu_name,parent_id,order_num,path,menu_type,visible,status,perms,create_by,create_time)
            SELECT :label,menu_id,5,'','F','1','0',:permission,'migration_hf_07',CURRENT_TIMESTAMP
            FROM sys_menu WHERE path='studio-project-permissions'
            AND NOT EXISTS (SELECT 1 FROM sys_menu WHERE perms=:permission)""").bindparams(
                label=label, permission=permission
            )
        )


def downgrade():
    raise RuntimeError('元素历史修订不允许自动回退删除')
