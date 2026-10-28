"""供应商输出发现的短事务，不下载文件、不修改费用。"""

from dataclasses import replace
from module_higgsfield.dao.generated_output_dao import GeneratedOutputDao
from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.entity.vo.generated_output_vo import DiscoveredOutput
from module_higgsfield.service.job_lease_service import JobLeaseService
from module_higgsfield.service.output_source_crypto_service import OutputSourceCryptoService
from module_higgsfield.service.project_workspace_service import WorkspaceService


class OutputDiscoveryService:
    @classmethod
    async def record(cls, db, lease, outputs: list[DiscoveredOutput], *, crypto=None, complete=False):
        """complete 仅用于适配器已确认全部生成结果的响应；不代表媒体已归档或费用已确认。"""
        if type(complete) is not bool:
            raise ValueError('完成标志必须为布尔值')
        if not 1 <= len(outputs) <= 1000 or len({item.ordinal for item in outputs}) != len(outputs):
            raise ValueError('输出批次必须包含1至1000个不同序号')
        crypto = crypto or (OutputSourceCryptoService() if any(item.kind != 'text' for item in outputs) else None)
        try:
            job, now = await JobLeaseService.guard(db, lease)
            if job.orchestration_state not in {'2', '3', '4'}:
                WorkspaceService.conflict('OUTPUT_DISCOVERY_INVALID', '当前任务阶段不能登记供应商输出')
            existing = {row.ordinal: row for row in await GeneratedOutputDao.for_job(db, job.job_id)}
            added = False
            for item in sorted(outputs, key=lambda item: item.ordinal):
                metadata = item.actual_metadata.model_dump(by_alias=True, exclude_none=True)
                previous = existing.get(item.ordinal)
                if previous:
                    # 重复发现不覆盖已归档文件或已失败状态；地址刷新走独立归档恢复流程。
                    if (
                        previous.kind != item.kind
                        or previous.text_content != item.text
                        or previous.actual_metadata != metadata
                    ):
                        WorkspaceService.conflict(
                            'OUTPUT_IDENTITY_CONFLICT', '相同任务输出序号对应不同内容，需核查供应商结果'
                        )
                    continue
                values = dict(
                    job_id=job.job_id,
                    ordinal=item.ordinal,
                    kind=item.kind,
                    text_content=item.text,
                    archive_state='5' if item.kind == 'text' else '0',
                    actual_metadata=metadata,
                    source_url_ciphertext=crypto.encrypt(item.source_url.get_secret_value(), job.job_id, item.ordinal)
                    if item.source_url
                    else None,
                    source_expires_time=item.source_expires_time,
                    next_retry_time=now if item.kind != 'text' else None,
                    create_by=lease.worker,
                    update_by=lease.worker,
                    create_time=now,
                    update_time=now,
                )
                row = await GeneratedOutputDao.add(db, values)
                job.event_sequence += 1
                await JobEventDao.output(db, job, row, now, lease.worker)
                added = True
            if added or complete:
                job.revision += 1
                job.update_time, job.update_by = now, lease.worker
            if complete:
                # 同步返回结果允许没有上游任务ID，不能为满足异步协议伪造编号。
                job.orchestration_state, job.upstream_state = '5', '3'
                job.finished_time = now
                job.next_action_time = None
                job.lease_owner = None
                job.lease_until = None
                job.event_sequence += 1
                await JobEventDao.state(db, job, now, lease.worker)
            result = replace(lease, revision=job.revision)
            await db.commit()
            return result
        except Exception:
            await db.rollback()
            raise
