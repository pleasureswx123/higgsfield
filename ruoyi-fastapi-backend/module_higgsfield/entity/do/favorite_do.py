"""个人收藏身份，目标访问权限不由此表授予。"""
from sqlalchemy import BigInteger, CHAR, CheckConstraint, Column, Index, text
from module_higgsfield.entity.do.asset_do import ContentRecord


class HfFavorite(ContentRecord):
    __tablename__ = 'hf_favorite'
    __table_args__ = (
        CheckConstraint("user_id>0 AND num_nonnulls(element_id,asset_id,output_id)=1 "
            "AND (element_id IS NULL OR element_id>0) AND (asset_id IS NULL OR asset_id>0) "
            "AND (output_id IS NULL OR output_id>0) AND del_flag IN ('0','2')", name='ck_hf_favorite_target'),
        Index('uq_hf_favorite_element_id', 'user_id', 'element_id', unique=True, postgresql_where=text('element_id IS NOT NULL')),
        Index('uq_hf_favorite_asset_id', 'user_id', 'asset_id', unique=True, postgresql_where=text('asset_id IS NOT NULL')),
        Index('uq_hf_favorite_output_id', 'user_id', 'output_id', unique=True, postgresql_where=text('output_id IS NOT NULL')),
        Index('ix_hf_favorite_user', 'user_id', 'del_flag', 'create_time', 'favorite_id'),
        {'comment': '个人收藏关系，不创建内容访问授权', 'info': {'migration_managed': True}},
    )
    favorite_id = Column(BigInteger, primary_key=True, autoincrement=True, comment='收藏ID')
    user_id = Column(BigInteger, nullable=False, comment='收藏用户ID')
    element_id = Column(BigInteger, comment='目标元素ID')
    asset_id = Column(BigInteger, comment='目标素材ID')
    output_id = Column(BigInteger, comment='目标作品ID')
    del_flag = Column(CHAR(1), nullable=False, server_default='0', comment='收藏状态：0存在2取消')
