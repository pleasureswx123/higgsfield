"""治理范围和制作成员权限独立；状态转换不取消已有供应商任务。"""
from module_higgsfield.dao.project_governance_dao import ProjectGovernanceDao
from module_higgsfield.dao.price_source_dao import PriceSourceDao
from module_higgsfield.service.admin_scope_service import AdminScopeService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService
from common.vo import PageModel


class ProjectGovernanceService:
    @classmethod
    async def listing(cls, db, user, query):
        actor, roles = await AdminScopeService.context(db, user, 'project:govern')
        rows, total = await ProjectGovernanceDao.page(db, query, actor, roles)
        return PageModel(rows=[cls.result(row) for row in rows], total=total,
                         pageNum=query.page_num, pageSize=query.page_size,
                         hasNext=query.page_num * query.page_size < total)

    TRANSITIONS = {'pause': ({'0'}, '1'), 'resume': ({'1'}, '0'),
                   'archive': ({'0', '1'}, '2'), 'restore': ({'2'}, '0')}

    @staticmethod
    def result(row):
        return {'id': str(row.project_id), 'name': row.project_name,
                'status': ('active', 'paused', 'archived', 'pending_delete')[int(row.status)],
                'revision': str(row.revision), 'createTime': row.create_time.isoformat(),
                'updateTime': row.update_time.isoformat()}

    @classmethod
    async def change(cls, db, user, identity, payload, key):
        path, prefix = f'/projects/{identity}/governance', '/api/admin/v1'
        data = payload.model_dump(by_alias=True)
        try:
            await AdminScopeService.project(db, user, identity, 'project:govern')
            await WriteService.lock(db, user, path, key, api_prefix=prefix)
            row = await ProjectGovernanceDao.locked(db, identity)
            # 锁后重验范围和删除状态；治理操作允许从暂停或归档恢复。
            await AdminScopeService.project(db, user, identity, 'project:govern')
            replay = await WriteService.replay(db, user, path, key, data, api_prefix=prefix)
            if replay:
                await db.commit()
                return replay, True
            WorkspaceService.check_revision(row, payload.revision)
            sources, target = cls.TRANSITIONS[payload.action]
            if row.status not in sources:
                WorkspaceService.conflict('PROJECT_GOVERNANCE_STATE_INVALID', '当前项目状态不允许此治理操作')
            before = cls.result(row)
            audit = WriteService.audit(user)
            row.status = target
            row.archived_time = audit['update_time'] if target == '2' else None
            row.revision += 1
            row.update_by, row.update_time = audit['update_by'], audit['update_time']
            after = cls.result(row)
            await PriceSourceDao.audit(db, dict(
                actor_id=user.user.user_id, actor_kind='user', project_id=identity,
                object_type='project', object_id=str(identity), action=payload.action,
                reason=payload.reason, request_id=WriteService.digest({'path': path, 'key': key}),
                before_after={'before': before, 'after': after}, **audit,
            ))
            return await WriteService.finish(db, user, path, key, data, after, 'project', identity, api_prefix=prefix)
        except Exception:
            await db.rollback()
            raise
