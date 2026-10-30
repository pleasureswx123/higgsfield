"""制作端不投影财务明细，费用查询统一走后台管理范围鉴权。"""


class TaskBillingReadService:
    @staticmethod
    async def read(db, job, allowed):
        return {'billingVisibility': 'hidden'}
