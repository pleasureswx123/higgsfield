"""仅展示已知状态和脱敏调用定位，不把恢复建议宣称为已执行事实。"""
from common.vo import PageModel
from exceptions.exception import PermissionException, ServiceWarning
from module_higgsfield.dao.incident_read_dao import IncidentReadDao
from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.dao.job_lease_dao import JobLeaseDao
from module_higgsfield.service.incident_requery_service import IncidentRequeryService
from module_higgsfield.service.incident_tracking_service import IncidentTrackingService
from module_higgsfield.service.incident_rejection_service import IncidentRejectionService
from module_higgsfield.dao.incident_rejection_dao import IncidentRejectionDao
from module_higgsfield.dao.provider_call_dao import ProviderCallDao
from module_higgsfield.service.admin_scope_service import AdminScopeService
from module_higgsfield.service.project_workspace_service import WorkspaceService


class IncidentReadService:
    @staticmethod
    def result(row, summary, call):
        orchestration = JobEventDao.ORCHESTRATION[int(row.orchestration_state)]
        upstream = JobEventDao.UPSTREAM[int(row.upstream_state)]
        fact = f'编排状态：{orchestration}；上游状态：{upstream}；归档失败或过期输出数：{summary["failed"]}'
        if call:
            fact += f'；最近调用受理事实：{call.acceptance}'
        return {'jobId': str(row.job_id), 'projectId': str(row.project_id), 'actorId': str(row.actor_id),
                'revision': str(row.revision), 'orchestrationState': orchestration, 'upstreamState': upstream,
                'archiveSummary': summary, 'billingState': ('pending', 'calculated', 'confirmed', 'disputed')[int(row.billing_state)],
                'lastKnownFact': fact, 'nextActionAt': row.next_action_time.isoformat() if row.next_action_time else None,
                'createTime': row.create_time.isoformat(), 'updateTime': row.update_time.isoformat(),
                # 列表只读；详情单独核验恢复权限及当前源有效性。
                'allowedActions': [], 'evidenceRefs': [f'provider-call:{call.call_id}'] if call else []}

    @classmethod
    async def listing(cls, db, user, query):
        actor, roles = await AdminScopeService.context(db, user, 'operations:read')
        rows, total = await IncidentReadDao.page(db, query, actor, roles)
        summaries, calls = await IncidentReadDao.evidence(db, [row.job_id for row in rows])
        return PageModel(rows=[cls.result(row, summaries[row.job_id], calls.get(row.job_id)) for row in rows],
                         total=total, pageNum=query.page_num, pageSize=query.page_size,
                         hasNext=query.page_num * query.page_size < total)

    @classmethod
    async def detail(cls, db, user, identity):
        actor, roles = await AdminScopeService.context(db, user, 'operations:read')
        row = await IncidentReadDao.detail(db, identity, actor, roles)
        if row is None:
            WorkspaceService.conflict('RESOURCE_NOT_FOUND', '任务不存在或不在管理范围内')
        summaries, calls = await IncidentReadDao.evidence(db, [row.job_id])
        result = cls.result(row, summaries[row.job_id], calls.get(row.job_id))
        if 'operations:recover' in user.permissions or '*:*:*' in user.permissions:
            try:
                await AdminScopeService.project(db, user, row.project_id, 'operations:recover')
            except (PermissionException, ServiceWarning):
                pass
            else:
                if await IncidentReadDao.retryable_archive(db, row.job_id):
                    result['allowedActions'] = ['retry_archive']
                if IncidentRequeryService.eligible(row, await JobLeaseDao.now(db)):
                    result['allowedActions'].append('requery')
                if IncidentTrackingService.eligible(row, await JobLeaseDao.now(db)):
                    result['allowedActions'].append('close_tracking')
                if IncidentRejectionService.eligible(row, await JobLeaseDao.now(db)) and not await IncidentRejectionDao.contradictory(db, row.job_id):
                    evidence = await IncidentRejectionDao.candidate(db, row.job_id)
                    original = await ProviderCallDao.submission(db, row.job_id)
                    try:
                        IncidentRejectionService.validate_evidence(row, original, evidence)
                    except ServiceWarning:
                        pass
                    else:
                        result['allowedActions'].append('confirm_not_accepted')
                        reference = f'provider-call:{evidence.call_id}'
                        if reference not in result['evidenceRefs']:
                            result['evidenceRefs'].append(reference)
        return result
