from sqlalchemy import select, func
from module_higgsfield.entity.do.cost_center_do import HfCostCenter


class CostCenterDao:
    @staticmethod
    async def page(db, query):
        condition = HfCostCenter.active == 'Y'
        total = await db.scalar(select(func.count()).select_from(HfCostCenter).where(condition))
        rows = (await db.scalars(select(HfCostCenter).where(condition).order_by(HfCostCenter.cost_center_id)
            .offset((query.page_num - 1) * query.page_size).limit(query.page_size))).all()
        return rows, total
