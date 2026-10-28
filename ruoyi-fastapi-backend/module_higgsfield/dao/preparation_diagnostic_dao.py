"""准备阶段异常复用只追加审计事实，查询限定任务对象及动作。"""
from sqlalchemy import select
from module_higgsfield.entity.do.audit_do import HfAuditLog


class PreparationDiagnosticDao:
    @staticmethod
    async def latest(db, job):
        return await db.scalar(select(HfAuditLog).where(
            HfAuditLog.object_type == 'creation_job', HfAuditLog.object_id == str(job.job_id),
            HfAuditLog.project_id == job.project_id, HfAuditLog.action == 'generation.prepare.deferred',
        ).order_by(HfAuditLog.audit_id.desc()).limit(1))

    @staticmethod
    async def add(db, job, now, worker, code):
        db.add(HfAuditLog(actor_kind='system', project_id=job.project_id, object_type='creation_job',
            object_id=str(job.job_id), action='generation.prepare.deferred',
            request_id=f'job:{job.job_id}:revision:{job.revision}',
            before_after={'code': code, 'revision': str(job.revision)},
            create_by=worker, update_by=worker, create_time=now, update_time=now))
        await db.flush()
