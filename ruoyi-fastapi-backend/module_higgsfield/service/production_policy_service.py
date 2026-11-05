"""多人制作的容量与恢复边界；参数缺失采用有界默认值，非法配置关闭新受理。"""
from module_higgsfield.dao.production_policy_dao import ProductionPolicyDao
from module_higgsfield.service.project_workspace_service import WorkspaceService


class ProductionPolicyService:
    DEFAULTS = {
        'userPending': 20, 'projectPending': 200, 'platformPending': 1000,
        'videoTrackingSeconds': 7200, 'archiveMaxAttempts': 5,
        'archiveRetryBaseSeconds': 60, 'archiveRetryMaxSeconds': 1800,
    }
    PREFIX = 'hf.production.'

    @classmethod
    async def read(cls, db):
        values = await ProductionPolicyDao.settings(db, [cls.PREFIX + name for name in cls.DEFAULTS])
        result = {}
        for name, default in cls.DEFAULTS.items():
            raw = values.get(cls.PREFIX + name, str(default))
            if not isinstance(raw, str) or not raw.isascii() or not raw.isdecimal() or not 1 <= int(raw) <= 1000000:
                WorkspaceService.conflict('PRODUCTION_POLICY_INVALID', '制作调度参数无效，请管理员检查参数配置')
            result[name] = int(raw)
        return result

    @classmethod
    async def admit(cls, db, actor_id, project_id):
        counts = await ProductionPolicyDao.queue_counts(db, actor_id, project_id)
        policy = await cls.read(db)
        for name, count, label in zip(('platformPending', 'userPending', 'projectPending'), counts,
                                      ('平台', '你', '当前项目')):
            if count >= policy[name]:
                WorkspaceService.conflict('GENERATION_QUEUE_FULL',
                    f'{label}的待处理任务已达上限（{policy[name]}个），请等待任务完成或处理异常任务后再生成')
