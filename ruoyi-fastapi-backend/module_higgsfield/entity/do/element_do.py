"""元素身份与不可变修订；业务关系由事务服务校验，不使用物理外键。"""

from sqlalchemy import CHAR, BigInteger, CheckConstraint, Column, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB

from module_higgsfield.entity.do.asset_do import ContentRecord


class HfElement(ContentRecord):
    __tablename__ = 'hf_element'
    __table_args__ = (
        UniqueConstraint('space_id', 'alias', name='uq_hf_element_alias'),
        CheckConstraint("category IN ('character','scene','prop','other')", name='ck_hf_element_category'),
        CheckConstraint("work_status IN ('0','1','2','3','4')", name='ck_hf_element_status'),
        CheckConstraint("del_flag IN ('0','2') AND revision > 0", name='ck_hf_element_lifecycle'),
        Index(
            'ix_hf_element_space',
            'space_id',
            'category',
            'create_time',
            'element_id',
            postgresql_where=text("del_flag='0'"),
        ),
        {'comment': '元素身份与当前修订指针', 'info': {'migration_managed': True}},
    )
    element_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='元素ID')
    space_id = Column(BigInteger, nullable=False, comment='所属空间ID')
    element_name = Column(String(200), nullable=False, comment='元素展示名称')
    alias = Column(String(100), nullable=False, comment='空间内唯一业务别名，删除后保留')
    category = Column(String(32), nullable=False, comment='分类：角色场景道具其他')
    create_user_id = Column(BigInteger, nullable=False, comment='创建用户ID')
    current_revision_id = Column(BigInteger, comment='当前不可变修订ID')
    performer_id = Column(BigInteger, comment='负责人的有效项目成员用户ID')
    folder_id = Column(BigInteger, comment='同空间元素目录ID，空为根目录')
    work_status = Column(CHAR(1), nullable=False, server_default='0', comment='0未开始1制作中2待审3通过4驳回')
    revision = Column(BigInteger, nullable=False, server_default='1', comment='身份并发版本')
    del_flag = Column(CHAR(1), nullable=False, server_default='0', comment='删除标志：0存在2删除')


class HfElementRevision(ContentRecord):
    __tablename__ = 'hf_element_revision'
    __table_args__ = (
        UniqueConstraint('element_id', 'revision_no', name='uq_hf_element_revision_no'),
        UniqueConstraint('element_id', 'revision_id', name='uq_hf_element_revision_identity'),
        CheckConstraint('revision_no > 0', name='ck_hf_element_revision_no'),
        CheckConstraint("jsonb_typeof(property_snapshot)='array'", name='ck_hf_element_property_snapshot'),
        {'comment': '元素不可变生成资料修订', 'info': {'migration_managed': True}},
    )
    revision_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='修订ID')
    element_id = Column(BigInteger, nullable=False, comment='元素身份ID')
    revision_no = Column(Integer, nullable=False, comment='递增内部修订号')
    description = Column(Text, nullable=False, server_default='', comment='参与生成的描述')
    property_snapshot = Column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb"), comment='属性定义版本和值的不可变快照'
    )
    create_user_id = Column(BigInteger, nullable=False, comment='修订创建用户ID')


class HfElementRevisionLabel(ContentRecord):
    __tablename__ = 'hf_element_revision_label'
    __table_args__ = (
        UniqueConstraint('element_revision_id', name='uq_hf_element_label_revision'),
        CheckConstraint('revision > 0', name='ck_hf_element_label_revision'),
        {'comment': '元素修订展示标签，不参与生成身份', 'info': {'migration_managed': True}},
    )
    label_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='标签记录ID')
    element_revision_id = Column(BigInteger, nullable=False, comment='元素修订ID')
    label = Column(String(100), nullable=False, server_default='', comment='用户展示标签')
    revision = Column(BigInteger, nullable=False, server_default='1', comment='标签并发版本')
    update_user_id = Column(BigInteger, nullable=False, comment='标签修改用户ID')


class HfElementRevisionMedia(ContentRecord):
    __tablename__ = 'hf_element_revision_media'
    __table_args__ = (
        UniqueConstraint('element_revision_id', 'ordinal', name='uq_hf_element_media_order'),
        UniqueConstraint('element_revision_id', 'asset_version_id', name='uq_hf_element_media_asset'),
        CheckConstraint("ordinal >= 0 AND is_primary IN ('Y','N')", name='ck_hf_element_media_values'),
        Index(
            'uq_hf_element_media_primary', 'element_revision_id', unique=True, postgresql_where=text("is_primary='Y'")
        ),
        {'comment': '元素修订固定素材多图与顺序', 'info': {'migration_managed': True}},
    )
    media_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='修订媒体ID')
    element_revision_id = Column(BigInteger, nullable=False, comment='元素修订ID')
    asset_version_id = Column(BigInteger, nullable=False, comment='固定素材版本ID')
    ordinal = Column(Integer, nullable=False, comment='媒体排序序号')
    is_primary = Column(CHAR(1), nullable=False, server_default='N', comment='是否主图：Y是N否')


class HfPropertyDefinition(ContentRecord):
    __tablename__ = 'hf_property_definition'
    __table_args__ = (
        UniqueConstraint('space_id', 'property_key', 'version_no', name='uq_hf_property_version'),
        CheckConstraint('version_no > 0', name='ck_hf_property_version'),
        CheckConstraint("value_type IN ('text','single_select','multi_select')", name='ck_hf_property_type'),
        CheckConstraint("jsonb_typeof(options)='array'", name='ck_hf_property_options'),
        {'comment': '元素属性定义不可变版本', 'info': {'migration_managed': True}},
    )
    property_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='属性定义版本ID')
    space_id = Column(BigInteger, nullable=False, comment='定义所属空间ID')
    property_key = Column(String(100), nullable=False, comment='稳定属性键')
    version_no = Column(Integer, nullable=False, comment='属性定义内部版本号')
    property_name = Column(String(200), nullable=False, comment='属性显示名称')
    value_type = Column(String(32), nullable=False, comment='文本、多选或历史单选')
    options = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"), comment='合法选项列表')
