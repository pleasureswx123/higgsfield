"""与任务结果事务共同追加用量，去重后不重复产生修订或消费。"""

from module_higgsfield.dao.provider_call_dao import ProviderCallDao
from module_higgsfield.dao.usage_dao import UsageDao
from module_higgsfield.entity.do.usage_do import HfBillingSubject, HfUsageRecord
from module_higgsfield.entity.vo.usage_fact_vo import UsageFact
from module_higgsfield.service.project_workspace_service import WorkspaceService


class UsageRecordService:
    @staticmethod
    async def append(db, job, source_call, fact: UsageFact, *, now, worker):
        """调用方必须已锁任务并在同事务更新聚合版本与事件；本方法不提交事务。

        新修订保留证据但不代表自动取代旧修订进行结算；后续计价须检查修订可信性。
        """
        expected = 'image' if job.kind == 'image' else 'video_poll' if job.kind == 'video' else None
        if (
            expected is None
            or source_call.job_id != job.job_id
            or source_call.operation != expected
            or source_call.state != '2'
            or source_call.credential_version_id != job.credential_version_id
        ):
            WorkspaceService.conflict('USAGE_SOURCE_INVALID', '用量调用与原生成任务不一致或尚未完成')
        expected_parser = 'videoplus-image-usage-v1' if job.kind == 'image' else 'videoplus-video-usage-v1'
        if fact.parser_version != expected_parser:
            WorkspaceService.conflict('USAGE_SOURCE_INVALID', '用量解析版本与任务类型不一致')
        origin = source_call if job.kind == 'image' else await ProviderCallDao.submission(db, job.job_id)
        if (
            origin is None
            or origin.operation != ('image' if job.kind == 'image' else 'video_submit')
            or origin.state != '2'
            or origin.acceptance != 'accepted'
            or origin.account_id != source_call.account_id
            or origin.credential_version_id != source_call.credential_version_id
        ):
            WorkspaceService.conflict('USAGE_ORIGIN_INVALID', '缺少原始受理调用，不能按查询次数创建计费对象')
        audit = dict(create_by=worker, update_by=worker, create_time=now, update_time=now)
        subject = await UsageDao.subject(db, origin.call_id)
        if subject is None:
            subject = await UsageDao.add(
                db,
                HfBillingSubject,
                dict(
                    account_id=origin.account_id,
                    job_id=job.job_id,
                    origin_call_id=origin.call_id,
                    subject_kind='generation',
                    identity_key=f'call:{origin.call_id}',
                    provider_object_id=job.upstream_task_id if job.kind == 'video' else None,
                    **audit,
                ),
            )
        if subject.job_id != job.job_id or subject.account_id != source_call.account_id:
            WorkspaceService.conflict('USAGE_SUBJECT_CONFLICT', '计费对象归属与调用不一致')
        previous = await UsageDao.by_hash(db, subject.subject_id, fact.payload_hash)
        if previous is not None:
            return previous, False
        latest = await UsageDao.latest(db, subject.subject_id)
        values = fact.model_dump(exclude={'issues'})
        row = await UsageDao.add(
            db,
            HfUsageRecord,
            values
            | dict(
                subject_id=subject.subject_id,
                call_id=source_call.call_id,
                revision_no=latest.revision_no + 1 if latest else 1,
                **audit,
            ),
        )
        return row, True
