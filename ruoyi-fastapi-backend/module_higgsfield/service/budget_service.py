"""预算定义生命周期；不因启停而释放已有任务的预占。"""

from common.vo import PageModel
from module_higgsfield.dao.budget_dao import BudgetDao
from module_higgsfield.dao.price_source_dao import PriceSourceDao
from module_higgsfield.service.admin_scope_service import AdminScopeService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService


class BudgetService:
    @staticmethod
    def result(row):
        return {
            'id': str(row.budget_id),
            'subject': {'projectId': str(row.project_id)} if row.project_id else {'userId': str(row.user_id)},
            'purpose': row.purpose,
            'currency': row.currency,
            'cycleKind': row.cycle_kind,
            'businessTimezone': row.business_timezone,
            'active': row.active == 'Y',
            'revision': str(row.revision),
        }

    @classmethod
    async def listing(cls, db, user, query):
        actor, roles = await AdminScopeService.context(db, user, 'billing:budget:read')
        rows, total = await BudgetDao.page(db, query, actor, roles)
        return PageModel(
            rows=[cls.result(row) for row in rows],
            total=total,
            pageNum=query.page_num,
            pageSize=query.page_size,
            hasNext=query.page_num * query.page_size < total,
        )

    @classmethod
    async def save(cls, db, user, payload, key, identity=None):
        path = '/budgets' + (f'/{identity}' if identity else '')
        prefix, method = '/api/admin/v1', 'PUT' if identity else 'POST'
        data = payload.model_dump(by_alias=True)
        try:
            actor, roles = await AdminScopeService.context(db, user, 'billing:budget')
            await WriteService.lock(db, user, path, key, api_prefix=prefix)
            if identity:
                row = await BudgetDao.get(db, identity)
                if row is None:
                    WorkspaceService.conflict('BUDGET_NOT_FOUND', '预算不存在或不在管理范围内')
                kind, subject_id = ('project', row.project_id) if row.project_id else ('user', row.user_id)
            else:
                kind, subject_id = (
                    ('project', int(payload.subject.project_id))
                    if payload.subject.project_id
                    else ('user', int(payload.subject.user_id))
                )
            purpose = row.purpose if identity else payload.purpose
            if purpose == 'procurement':
                await AdminScopeService.global_access(db, user, 'billing:budget')
            await BudgetDao.lock_subject(db, kind, subject_id)
            subject = await BudgetDao.subject(db, kind, subject_id, actor, roles)
            if subject is None:
                WorkspaceService.conflict('BUDGET_SUBJECT_NOT_FOUND', '预算主体不存在或不在管理范围内')
            replay = await WriteService.replay(db, user, path, key, data, method, api_prefix=prefix)
            if replay:
                await db.commit()
                return replay, True
            audit = WriteService.audit(user)
            before = None
            if identity:
                row = await BudgetDao.get(db, identity, lock=True)
                WorkspaceService.check_revision(row, payload.revision)
                before = cls.result(row)
                row.active = 'Y' if payload.active else 'N'
                row.revision += 1
                row.update_by, row.update_time = audit['update_by'], audit['update_time']
            else:
                if subject.status != '0':
                    WorkspaceService.conflict('BUDGET_SUBJECT_INACTIVE', '停用用户或非活动项目不能新建预算')
                if await BudgetDao.existing(db, payload):
                    WorkspaceService.conflict('BUDGET_EXISTS', '相同主体、口径、币种和周期的预算已存在')
                row = await BudgetDao.add(
                    db,
                    dict(
                        project_id=subject_id if kind == 'project' else None,
                        user_id=subject_id if kind == 'user' else None,
                        purpose=payload.purpose,
                        currency=payload.currency,
                        cycle_kind=payload.cycle_kind,
                        business_timezone=payload.business_timezone,
                        **audit,
                    ),
                )
            after = cls.result(row)
            await PriceSourceDao.audit(
                db,
                dict(
                    actor_id=user.user.user_id,
                    actor_kind='user',
                    project_id=row.project_id,
                    object_type='budget',
                    object_id=str(row.budget_id),
                    action='set_active' if identity else 'create',
                    request_id=WriteService.digest({'path': path, 'key': key}),
                    before_after={'before': before, 'after': after},
                    **audit,
                ),
            )
            return await WriteService.finish(
                db, user, path, key, data, after, 'budget', row.budget_id, method, api_prefix=prefix
            )
        except Exception:
            await db.rollback()
            raise
