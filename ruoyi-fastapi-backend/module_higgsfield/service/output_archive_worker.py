"""结果归档调度：短事务占用与续期，事务外下载，版本栅栏登记。"""

import asyncio
from contextlib import suppress

from exceptions.exception import ServiceWarning
from module_higgsfield.dao.generated_output_dao import GeneratedOutputDao
from module_higgsfield.dao.job_lease_dao import JobLeaseDao
from module_higgsfield.service.job_lease_service import JobLeaseService
from module_higgsfield.service.output_archive_service import OutputArchiveService


class OutputArchiveWorker:
    def __init__(self, sessions, worker, downloader, crypto, *, batch_size=4, lease_seconds=60):
        JobLeaseService.validate_worker(worker)
        if type(batch_size) is not int or not 1 <= batch_size <= 100:
            raise ValueError('归档批量必须为1至100')
        if type(lease_seconds) is not int or not 5 <= lease_seconds <= 300:
            raise ValueError('归档占用时长必须为5至300秒')
        self.sessions, self.worker = sessions, worker
        self.downloader, self.crypto = downloader, crypto
        self.batch_size, self.lease_seconds = batch_size, lease_seconds

    async def change(self, identity, revision, action):
        async with self.sessions() as db:
            return await OutputArchiveService.mutate(
                db,
                identity,
                revision=revision,
                action=action,
                worker=self.worker,
                delay_seconds=self.lease_seconds,
            )

    async def heartbeat(self, identity, revision):
        while True:
            await asyncio.sleep(self.lease_seconds / 3)
            await self.change(identity, revision, 'renew')

    async def download_and_register(self, identity, revision):
        async with self.sessions() as db:
            output = await GeneratedOutputDao.get(db, identity)
            if output is None or output.revision != revision or output.archive_state != '1':
                raise ValueError('归档占用已变化')
            url = self.crypto.decrypt(output.source_url_ciphertext, output.job_id, output.ordinal)
            kind = output.kind
        # 会话已关闭，网络和文件操作不持有数据库事务。
        facts = await self.downloader.download(url, kind=kind)
        async with self.sessions() as db:
            return await OutputArchiveService.register_download(
                db,
                identity,
                revision=revision,
                worker=self.worker,
                facts=facts,
            )

    async def process(self, identity, revision):
        try:
            claimed = await self.change(identity, revision, 'begin')
        except ServiceWarning:
            return {'outputId': str(identity), 'status': 'skipped'}
        if claimed['archiveState'] == 'source_expired':
            return {'outputId': str(identity), 'status': 'source_expired'}
        revision = int(claimed['revision'])
        work = asyncio.create_task(self.download_and_register(identity, revision))
        heartbeat = asyncio.create_task(self.heartbeat(identity, revision))
        try:
            done, _ = await asyncio.wait((work, heartbeat), return_when=asyncio.FIRST_COMPLETED)
            # 完成事实优先于恰在提交后发生的续期冲突。
            if work in done:
                await work
            else:
                await heartbeat
                raise RuntimeError('归档续期意外终止')
            return {'outputId': str(identity), 'status': 'archived'}
        except Exception:
            work.cancel()
            heartbeat.cancel()
            await asyncio.gather(work, heartbeat, return_exceptions=True)
            # 不输出源地址或原始异常；失败登记仍受旧版本栅栏约束。
            with suppress(Exception):
                await self.change(identity, revision, 'fail')
            return {'outputId': str(identity), 'status': 'failed'}
        finally:
            for task in (work, heartbeat):
                task.cancel()
            await asyncio.gather(work, heartbeat, return_exceptions=True)
            # 不删除已下载文件：提交结果不确定时可能已经绑定，交由证据清理流程处理。

    async def run_once(self):
        async with self.sessions() as db:
            candidates = await GeneratedOutputDao.archive_candidates(db, await JobLeaseDao.now(db), self.batch_size)
        return await asyncio.gather(*(self.process(identity, revision) for identity, revision in candidates))

    async def serve(self, stop):
        while not stop.is_set():
            await self.run_once()
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=1)
