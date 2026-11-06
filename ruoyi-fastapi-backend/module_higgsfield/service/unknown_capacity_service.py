"""未知结果只在保护期内占用本地调度名额；回收不代表上游结束或未计费。"""
from module_higgsfield.dao.unknown_capacity_dao import UnknownCapacityDao
from module_higgsfield.service.production_policy_service import ProductionPolicyService


class UnknownCapacityService:
    @staticmethod
    async def recover(db, now, worker):
        policy = await ProductionPolicyService.read(db)
        return await UnknownCapacityDao.release_expired(
            db, now, worker, policy['unknownCapacityHoldSeconds'])
