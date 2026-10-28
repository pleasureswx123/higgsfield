"""视频轮询短事务：查询失败只延后查询，状态与输出事实原子提交。"""

import re
import secrets
from dataclasses import replace
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.dao.provider_call_dao import ProviderCallDao
from module_higgsfield.entity.vo.video_provider_fact_vo import VideoProviderFact
from module_higgsfield.service.job_lease_service import JobLease, JobLeaseService
from module_higgsfield.service.output_discovery_service import OutputDiscoveryService
from module_higgsfield.service.output_source_crypto_service import OutputSourceCryptoService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.provider_job_binding_service import ProviderJobBindingService
from module_higgsfield.service.videoplus_response_service import VideoPlusResponseService
from module_higgsfield.service.usage_record_service import UsageRecordService

HTTP_MIN, HTTP_MAX = 100, 599


class ProviderPollService:
    @staticmethod
    async def begin(db: AsyncSession, lease: JobLease, request_hash: str) -> int:
        if not isinstance(request_hash, str) or not re.fullmatch('[0-9a-f]{64}', request_hash):
            raise ValueError('请求摘要必须是SHA256')
        try:
            job, now = await JobLeaseService.guard(db, lease)
            if job.kind != 'video' or job.orchestration_state != '4' or not job.upstream_task_id:
                WorkspaceService.conflict('PROVIDER_POLL_UNAVAILABLE', '只有已绑定上游任务的视频可查询')
            job, now, account, version, config = await ProviderJobBindingService.require(db, lease, job)
            for prior in await ProviderCallDao.sending_polls(db, job.job_id):
                if prior.request_metadata.get('fencingToken') == str(lease.fencing_token):
                    WorkspaceService.conflict('PROVIDER_POLL_EXISTS', '当前租约已有正在执行的查询')
                prior.state, prior.acceptance = '3', 'unknown'
                prior.finished_time = now
                prior.update_by, prior.update_time = lease.worker, now
                prior.response_metadata = {'recoveryReason': 'poll_lease_lost'}
            call = await ProviderCallDao.add(
                db,
                {
                    'job_id': job.job_id,
                    'account_id': account.account_id,
                    'credential_version_id': version.credential_version_id,
                    'operation': 'video_poll',
                    'request_hash': request_hash,
                    'state': '1',
                    'acceptance': 'unknown',
                    'request_metadata': {
                        'upstreamTaskId': job.upstream_task_id,
                        'connectionVersionId': str(config.connection_version_id),
                        'adapterVersion': config.adapter_version,
                        'fencingToken': str(lease.fencing_token),
                    },
                    'started_time': now,
                    'create_time': now,
                    'update_time': now,
                    'create_by': lease.worker,
                    'update_by': lease.worker,
                },
            )
            identity = call.call_id
            await db.commit()
            return identity
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    async def record(
        db: AsyncSession,
        lease: JobLease,
        call_id: int,
        *,
        http_status: int | None = None,
        body: object = None,
        transport: str = 'response',
        crypto: OutputSourceCryptoService | None = None,
    ) -> JobLease:
        if transport not in {'response', 'timeout', 'network_error'}:
            raise ValueError('未知传输结果')
        if transport == 'response':
            if type(http_status) is not int or not HTTP_MIN <= http_status <= HTTP_MAX:
                raise ValueError('响应必须有有效HTTP状态')
        elif http_status is not None or body is not None:
            raise ValueError('未收到响应不能提供HTTP状态或正文')
        try:
            job, now = await JobLeaseService.guard(db, lease)
            call = await ProviderCallDao.locked(db, call_id)
            if (
                call is None
                or call.job_id != job.job_id
                or call.operation != 'video_poll'
                or call.state != '1'
                or call.credential_version_id != job.credential_version_id
                or job.orchestration_state != '4'
                or call.request_metadata.get('upstreamTaskId') != job.upstream_task_id
                or call.request_metadata.get('fencingToken') != str(lease.fencing_token)
            ):
                WorkspaceService.conflict('PROVIDER_POLL_STALE', '查询结果不属于当前任务与租约')
            job, now = await JobLeaseService.guard(db, lease)
            fact = (
                VideoPlusResponseService.polling(http_status, body, expected_task_id=job.upstream_task_id)
                if transport == 'response'
                else VideoProviderFact(upstreamState='unknown', issues=['QUERY_TRANSPORT_UNKNOWN'])
            )
            call.state, call.acceptance = ('2', 'not_applicable') if transport == 'response' else ('3', 'unknown')
            call.http_status, call.finished_time = http_status, now
            call.update_by, call.update_time = lease.worker, now
            call.response_metadata = fact.model_dump(by_alias=True, exclude={'outputs'}, exclude_none=True) | {
                'transport': transport,
                'outputCount': len(fact.outputs),
            }
            usage_added = False
            if fact.upstream_state in {'succeeded', 'failed'} and fact.usage_fact is not None:
                _, usage_added = await UsageRecordService.append(
                    db,
                    job,
                    call,
                    fact.usage_fact,
                    now=now,
                    worker=lease.worker,
                )
            if fact.upstream_state == 'succeeded' and fact.outputs:
                await db.flush()
                return await OutputDiscoveryService.record(db, lease, fact.outputs, crypto=crypto, complete=True)
            upstream = {'queued': '1', 'running': '2', 'succeeded': '3', 'failed': '4', 'unknown': '6'}[
                fact.upstream_state
            ]
            # 后续查询故障或矛盾响应不能抹去已经明确的成功事实。
            if job.upstream_state == '3':
                upstream = '3'
            target = '5' if upstream == '4' else '4'
            changed = (job.orchestration_state, job.upstream_state) != (target, upstream)
            job.orchestration_state, job.upstream_state = target, upstream
            job.next_action_time = now + timedelta(seconds=30 + secrets.randbelow(31)) if target == '4' else None
            if target == '5':
                job.finished_time = now
            job.lease_owner, job.lease_until = None, None
            job.update_by, job.update_time = lease.worker, now
            if changed or usage_added:
                job.revision += 1
                job.event_sequence += 1
                await JobEventDao.state(db, job, now, lease.worker)
            result = replace(lease, revision=job.revision)
            await db.commit()
            return result
        except Exception:
            await db.rollback()
            raise
