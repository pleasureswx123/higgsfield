"""独立测试队列执行与恢复，实例间靠调用意图事务防重。"""
import asyncio
from datetime import timedelta
from module_higgsfield.dao.credential_test_dao import CredentialTestDao
from module_higgsfield.dao.job_lease_dao import JobLeaseDao
from module_higgsfield.service.credential_test_recovery_service import CredentialTestRecoveryService


class CredentialTestWorker:
    def __init__(self, executor, *, concurrency=4, handler_timeout=300, stale_after_seconds=600):
        if type(concurrency) is not int or not 1 <= concurrency <= 32:
            raise ValueError('测试工作器并发数必须在1到32之间')
        if type(handler_timeout) is not int or handler_timeout < 1:
            raise ValueError('测试处理超时必须为正整数')
        if stale_after_seconds <= handler_timeout + 60:
            raise ValueError('测试回收窗口必须超过执行超时至少60秒')
        self.executor, self.concurrency, self.timeout = executor, concurrency, handler_timeout
        self.recovery = CredentialTestRecoveryService(executor, stale_after_seconds=stale_after_seconds)

    async def run_once(self):
        async with self.executor.sessions() as db:
            now = await JobLeaseDao.now(db)
            pending, stale = await CredentialTestDao.candidates(db,
                now - timedelta(seconds=self.recovery.stale_after_seconds), self.concurrency)
        semaphore = asyncio.Semaphore(self.concurrency)
        async def handle(identity, recover):
            async with semaphore:
                try:
                    action = self.recovery.recover if recover else self.executor.execute
                    changed = await asyncio.wait_for(action(identity), timeout=self.timeout)
                    return {'testId': str(identity), 'status': 'handled' if changed else 'skipped'}
                except Exception:
                    try:
                        async with self.executor.sessions() as db:
                            row = await CredentialTestDao.locked(db, identity)
                            if row is not None and row.state == '0':
                                row.update_time = await JobLeaseDao.now(db)
                            await db.commit()
                    except Exception:
                        pass
                    # 不输出供应商、密钥、数据库异常正文。轮询下一批前暂停，避免错误热循环。
                    return {'testId': str(identity), 'status': 'failed'}
        return await asyncio.gather(*(handle(identity, True) for identity in stale),
                                    *(handle(identity, False) for identity in pending))

    async def serve(self, stop):
        while not stop.is_set():
            await self.run_once()
            try:
                await asyncio.wait_for(stop.wait(), timeout=5)
            except TimeoutError:
                pass
