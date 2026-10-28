"""按已持久化用量循环计价；短事务行锁支持多实例，不调用供应商。"""

import asyncio
import re

from module_higgsfield.dao.billing_dao import BillingDao
from module_higgsfield.dao.budget_reservation_dao import BudgetReservationDao
from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.service.billing_calculation_service import BillingCalculationService
from module_higgsfield.service.budget_settlement_service import BudgetSettlementService
from module_higgsfield.service.generation_read_service import GenerationReadService


class BillingWorker:
    def __init__(self, sessions, worker, *, batch_size=4):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', worker):
            raise ValueError('工作器标识无效')
        if type(batch_size) is not int or not 1 <= batch_size <= 100:
            raise ValueError('批次大小必须在1到100之间')
        self.sessions, self.worker, self.batch_size = sessions, worker, batch_size
        self.after = 0

    async def process(self, identity):
        async with self.sessions() as db:
            try:
                job = await BillingDao.job(db, identity)
                if job is None:
                    return {'jobId': str(identity), 'status': 'skipped'}
                now = await BillingDao.now(db)
                subjects = await BillingDao.subjects(db, identity)
                changed, platform_states = False, []
                for subject_id in subjects:
                    for purpose in ('platform', 'procurement'):
                        event, updated = await BillingCalculationService.calculate(
                            db, job=job, subject_id=subject_id, purpose=purpose, now=now, worker=self.worker
                        )
                        changed |= updated
                        if purpose == 'platform':
                            platform_states.append(event.state)
                changed |= await BudgetSettlementService.settle(db, identity, now=now, worker=self.worker)
                platform_states = [
                    event.state if event is not None else '0'
                    for _, event in await BudgetReservationDao.billing_facts(db, identity, 'platform')
                ]
                # 制作任务仅聚合平台计价状态，采购证据不透传到制作端。
                state = (
                    '3'
                    if '3' in platform_states
                    else '0'
                    if not platform_states or '0' in platform_states
                    else '2'
                    if all(value == '2' for value in platform_states)
                    else '1'
                )
                changed |= job.billing_state != state
                if changed:
                    job.billing_state = state
                    job.revision += 1
                    job.event_sequence += 1
                    job.update_by, job.update_time = self.worker, now
                    await JobEventDao.usage(
                        db, job, now, self.worker, await GenerationReadService.usage_state(db, identity)
                    )
                await db.commit()
                return {'jobId': str(identity), 'status': 'handled' if changed else 'skipped'}
            except Exception:
                await db.rollback()
                raise

    async def run_once(self):
        async with self.sessions() as db:
            identities = await BillingDao.candidates(db, self.after, self.batch_size)
            if not identities and self.after:
                self.after = 0
                identities = await BillingDao.candidates(db, self.after, self.batch_size)
        results = []
        for identity in identities:
            try:
                results.append(await self.process(identity))
            except Exception:
                # 不输出数据库或供应商证据正文；下一轮重新处理失败任务。
                results.append({'jobId': str(identity), 'status': 'failed'})
            self.after = identity
        return results

    async def serve(self, stop):
        while not stop.is_set():
            await self.run_once()
            try:
                await asyncio.wait_for(stop.wait(), timeout=2)
            except TimeoutError:
                pass
