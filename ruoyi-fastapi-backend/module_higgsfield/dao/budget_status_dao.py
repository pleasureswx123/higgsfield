"""预算状态只读快照，不创建周期或锁定额度。"""

from sqlalchemy import select, func, and_, or_
from module_higgsfield.entity.do.budget_do import HfBudget, HfBudgetPeriod


class BudgetStatusDao:
    @staticmethod
    async def current(db, project_id, user_id):
        return (
            await db.execute(
                select(HfBudget, HfBudgetPeriod)
                .outerjoin(
                    HfBudgetPeriod,
                    and_(
                        HfBudgetPeriod.budget_id == HfBudget.budget_id,
                        HfBudgetPeriod.period_start <= func.now(),
                        or_(HfBudgetPeriod.period_end.is_(None), HfBudgetPeriod.period_end > func.now()),
                    ),
                )
                .where(HfBudget.active == 'Y', or_(HfBudget.project_id == project_id, HfBudget.user_id == user_id))
                .order_by(HfBudget.budget_id, HfBudgetPeriod.period_id)
            )
        ).all()
