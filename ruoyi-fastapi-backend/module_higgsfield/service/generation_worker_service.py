"""有界并发调度与短会话续租，阶段处理器负责供应商协议。"""

import asyncio
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from module_higgsfield.entity.vo.generated_output_vo import DiscoveredOutput
from module_higgsfield.entity.vo.provider_submission_vo import ProviderSubmissionResult, ProviderSynchronousResult
from module_higgsfield.service.job_lease_service import JobLease, JobLeaseService
from module_higgsfield.service.job_transition_service import JobTransitionService
from module_higgsfield.service.output_discovery_service import OutputDiscoveryService
from module_higgsfield.service.output_source_crypto_service import OutputSourceCryptoService
from module_higgsfield.service.provider_poll_service import ProviderPollService
from module_higgsfield.service.provider_submission_result_service import ProviderSubmissionResultService
from module_higgsfield.service.provider_submit_intent_service import ProviderSubmitIntentService
from module_higgsfield.service.provider_synchronous_result_service import ProviderSynchronousResultService
from module_higgsfield.service.submission_reconciliation_service import SubmissionReconciliationService
from module_higgsfield.service.image_result_service import ImageResultService
from module_higgsfield.entity.vo.image_provider_fact_vo import ImageProviderFact
from module_higgsfield.service.preparation_diagnostic_service import PreparationDiagnosticService

MAX_CONCURRENCY = 100
MAX_HANDLER_SECONDS = 3600


class JobExecutionContext:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], lease: JobLease, lease_seconds: int) -> None:
        self.sessions = sessions
        self.lease = lease
        self.lease_seconds = lease_seconds
        self.closed = False
        self._lock = asyncio.Lock()

    async def renew(self) -> None:
        async with self._lock:
            if not self.closed:
                async with self.sessions() as db:
                    await JobLeaseService.renew(db, self.lease, lease_seconds=self.lease_seconds)

    async def begin_submission(self, request_hash: str) -> int:
        async with self._lock:
            if self.closed:
                raise RuntimeError('执行上下文已结束')
            async with self.sessions() as db:
                self.lease, call_id = await ProviderSubmitIntentService.begin(db, self.lease, request_hash)
            return call_id

    async def record_submission(
        self, call_id: int, result: ProviderSubmissionResult, *, recovery_evidence_id: int | None = None
    ) -> None:
        async with self._lock:
            if self.closed:
                raise RuntimeError('执行上下文已结束')
            async with self.sessions() as db:
                self.lease = await ProviderSubmissionResultService.record(
                    db, self.lease, call_id, result, recovery_evidence_id=recovery_evidence_id
                )
            self.closed = True

    async def record_synchronous(
        self, call_id: int, result: ProviderSynchronousResult, *, crypto: OutputSourceCryptoService | None = None
    ) -> None:
        async with self._lock:
            if self.closed:
                raise RuntimeError('执行上下文已结束')
            async with self.sessions() as db:
                self.lease = await ProviderSynchronousResultService.record(
                    db, self.lease, call_id, result, crypto=crypto
                )
            self.closed = True

    async def record_images(
        self,
        call_id: int,
        fact: ImageProviderFact,
        stored: dict[int, dict],
        *,
        http_status: int,
        recovery_evidence_id: int | None = None,
    ) -> None:
        async with self._lock:
            if self.closed:
                raise RuntimeError('执行上下文已结束')
            async with self.sessions() as db:
                self.lease = await ImageResultService.record(
                    db,
                    self.lease,
                    call_id,
                    fact,
                    stored,
                    http_status=http_status,
                    recovery_evidence_id=recovery_evidence_id,
                )
            self.closed = True

    async def reconcile_submission(self, submission_id: int, evidence_call_id: int) -> None:
        async with self._lock:
            if self.closed:
                raise RuntimeError('执行上下文已结束')
            async with self.sessions() as db:
                self.lease = await SubmissionReconciliationService.record(
                    db, self.lease, submission_id, evidence_call_id
                )
            self.closed = True

    async def begin_poll(self, request_hash: str) -> int:
        async with self._lock:
            if self.closed:
                raise RuntimeError('执行上下文已结束')
            async with self.sessions() as db:
                return await ProviderPollService.begin(db, self.lease, request_hash)

    async def record_poll(
        self,
        call_id: int,
        *,
        http_status: int | None = None,
        body: object = None,
        transport: str = 'response',
        crypto: OutputSourceCryptoService | None = None,
    ) -> None:
        async with self._lock:
            if self.closed:
                raise RuntimeError('执行上下文已结束')
            async with self.sessions() as db:
                self.lease = await ProviderPollService.record(
                    db, self.lease, call_id, http_status=http_status, body=body, transport=transport, crypto=crypto
                )
            self.closed = True

    async def advance(self, action: str, *, upstream_task_id: str | None = None, retry_after_seconds: int = 5) -> None:
        async with self._lock:
            if self.closed:
                raise RuntimeError('执行上下文已结束')
            async with self.sessions() as db:
                self.lease = await JobTransitionService.apply(
                    db,
                    self.lease,
                    action=action,
                    upstream_task_id=upstream_task_id,
                    retry_after_seconds=retry_after_seconds,
                )
            self.closed = action not in {'prepare', 'submit'}

    async def complete(
        self, outputs: list[DiscoveredOutput], *, crypto: OutputSourceCryptoService | None = None
    ) -> None:
        async with self._lock:
            if self.closed:
                raise RuntimeError('执行上下文已结束')
            async with self.sessions() as db:
                self.lease = await OutputDiscoveryService.record(db, self.lease, outputs, crypto=crypto, complete=True)
            self.closed = True

    async def defer(self, seconds: int, diagnostic_code: str | None = None) -> None:
        async with self._lock:
            if not self.closed:
                async with self.sessions() as db:
                    await JobLeaseService.release(db, self.lease, retry_after_seconds=seconds, diagnostic_code=diagnostic_code)
                self.closed = True


Handler = Callable[[JobExecutionContext], Awaitable[None]]


class GenerationWorkerService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        worker: str,
        handlers: dict[str, Handler],
        *,
        concurrency: int = 4,
        lease_seconds: int = 60,
        handler_timeout: float = 120,
        kinds: tuple[str, ...] | None = None,
    ) -> None:
        JobLeaseService.validate_worker(worker)
        JobLeaseService.validate_duration(lease_seconds)
        if (
            type(concurrency) is not int
            or not 1 <= concurrency <= MAX_CONCURRENCY
            or not 0 < handler_timeout <= MAX_HANDLER_SECONDS
        ):
            raise ValueError('并发数须为1到100，单阶段执行期限须为0到3600秒')
        if set(handlers) - {'prepare', 'reconcile_submission', 'poll'}:
            raise ValueError('未知调度阶段，提交未知任务不能注册重新提交处理器')
        self.sessions, self.worker, self.handlers = sessions, worker, dict(handlers)
        self.concurrency, self.lease_seconds, self.handler_timeout = concurrency, lease_seconds, handler_timeout
        self._batch_lock = asyncio.Lock()
        self.kinds = kinds

    async def _execute(self, lease: JobLease) -> dict:
        context = JobExecutionContext(self.sessions, lease, self.lease_seconds)
        handler = self.handlers.get(lease.action)
        if handler is None:
            try:
                await context.defer(30)
                return {'jobId': str(lease.job_id), 'status': 'handler_unavailable'}
            except Exception:
                return {'jobId': str(lease.job_id), 'status': 'lease_lost'}

        async def heartbeat() -> None:
            while True:
                await asyncio.sleep(self.lease_seconds / 3)
                await context.renew()

        async def work() -> None:
            async with asyncio.timeout(self.handler_timeout):
                await handler(context)

        task, renew = asyncio.create_task(work()), asyncio.create_task(heartbeat())
        status = 'handled'
        diagnostic_code = None
        try:
            done, _ = await asyncio.wait({task, renew}, return_when=asyncio.FIRST_COMPLETED)
            if renew in done:
                # 续租失败即停止旧执行者；不记录可能含供应商响应或秘密的异常正文。
                status = 'lease_lost'
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                context.closed = True
            else:
                await task
        except asyncio.CancelledError:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise
        except Exception as error:
            status = 'handler_failed'
            if lease.action == 'prepare':
                diagnostic_code = PreparationDiagnosticService.classify(error)
        finally:
            renew.cancel()
            await asyncio.gather(renew, return_exceptions=True)
            try:
                # 若已持久进入提交阶段，释放后下一轮领取会转为提交未知，绝不自动重发。
                await context.defer(30, diagnostic_code)
            except Exception:
                status = 'lease_lost'
        return {'jobId': str(lease.job_id), 'status': status}

    async def run_once(self) -> list[dict]:
        async with self._batch_lock:
            async with self.sessions() as db:
                leases = await JobLeaseService.claim(
                    db, self.worker, limit=self.concurrency, lease_seconds=self.lease_seconds, kinds=self.kinds
                )
            return list(await asyncio.gather(*(self._execute(lease) for lease in leases)))

    async def serve(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self.run_once()
            try:
                await asyncio.wait_for(stop.wait(), timeout=1)
            except TimeoutError:
                pass
