"""补齐制作平台项目状态字典。"""
from alembic import op
from sqlalchemy import text
revision = '20261027_02'
down_revision = '20261027_01'
branch_labels = None
depends_on = None


def upgrade():
    """复用框架字典，仅新增尚不存在的值。"""
    definitions = [
        ('hf_project_status', '项目状态', [('0','进行中'),('1','已暂停'),('2','已归档'),('3','待删除')]),
        ('hf_project_member_status', '项目成员状态', [('0','有效'),('1','已移除')]),
        ('hf_api_idempotency_record_state', '写请求状态', [('0','处理中'),('1','已完成'),('2','待恢复')]),
    ]
    for kind, label, values in definitions:
        op.execute(text("INSERT INTO sys_dict_type (dict_name,dict_type,status,create_by,create_time) SELECT :label,:kind,'0','migration_hf_02',CURRENT_TIMESTAMP WHERE NOT EXISTS (SELECT 1 FROM sys_dict_type WHERE dict_type=:kind)").bindparams(label=label,kind=kind))
        for order, (value, title) in enumerate(values):
            op.execute(text("INSERT INTO sys_dict_data (dict_sort,dict_label,dict_value,dict_type,is_default,status,create_by,create_time) SELECT :sort,:title,:value,:kind,'N','0','migration_hf_02',CURRENT_TIMESTAMP WHERE NOT EXISTS (SELECT 1 FROM sys_dict_data WHERE dict_type=:kind AND dict_value=:value)").bindparams(sort=order,title=title,value=value,kind=kind))


def downgrade():
    """不自动删除可能已被业务引用的字典。"""
    raise RuntimeError('项目字典可能已有引用，不支持自动删除回退')
