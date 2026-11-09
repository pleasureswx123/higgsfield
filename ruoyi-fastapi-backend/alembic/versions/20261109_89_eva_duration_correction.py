"""修正 EVA 2.5 接入时误录的时长枚举，保留历史任务快照并记录更正证据。"""
import json

from alembic import op
import sqlalchemy as sa

revision = '20261109_89'
down_revision = '20261105_88'
branch_labels = None
depends_on = None


def upgrade():
    # 这是用户确认的接入资料勘误，不改变供应商模型身份、价格及既有任务快照。
    # 仅匹配原错误枚举；管理员已调整的范围及其他模型不受影响。
    connection = op.get_bind()
    old = [-1, *range(4, 16)]
    new = [-1, *range(4, 31)]
    rows = connection.execute(sa.text("""
        SELECT model_version_id FROM hf_model_profile_version
        WHERE gateway_alias='mm-eva-sd-2.5'
          AND capabilities #> '{parametersSchema,properties,duration,enum}' = CAST(:old AS jsonb)
        FOR UPDATE
    """), {'old': json.dumps(old)}).scalars().all()
    for identity in rows:
        connection.execute(sa.text("""
            UPDATE hf_model_profile_version
            SET capabilities=jsonb_set(capabilities,
                    '{parametersSchema,properties,duration,enum}', CAST(:new AS jsonb)),
                revision=revision+1, update_by='migration_89', update_time=CURRENT_TIMESTAMP
            WHERE model_version_id=:id
        """), {'new': json.dumps(new), 'id': identity})
        connection.execute(sa.text("""
            INSERT INTO hf_audit_log
                (actor_kind,object_type,object_id,action,request_id,before_after,reason,
                 create_by,update_by,create_time,update_time)
            VALUES ('system','model_profile_version',:id,'model.duration_correction',:request,
                    CAST(:evidence AS jsonb),:reason,'migration_89','migration_89',
                    CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
        """), {
            'id': str(identity), 'request': f'migration_20261109_89_{identity}',
            'evidence': json.dumps({'before': {'durationEnum': old}, 'after': {'durationEnum': new}}),
            'reason': '2026-11-09 用户确认 mm-eva-sd-2.5 支持最长30秒，旧接入文档4～15秒为误录；未宣称完成30秒供应商实测。',
        })


def downgrade():
    # 能力勘误生效后可能已有30秒草稿及任务；回退代码不撤销事实、更改历史或缩减能力。
    pass
