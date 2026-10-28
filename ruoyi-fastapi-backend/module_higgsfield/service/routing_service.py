"""项目路由管理使用管理范围，不能借此读取项目制作内容。"""

from module_higgsfield.dao.routing_dao import RoutingDao
from module_higgsfield.service.admin_scope_service import AdminScopeService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService
from module_higgsfield.dao.provider_dao import ProviderDao
from module_higgsfield.entity.do.audit_do import HfAuditLog
from utils.time_util import TimezoneUtil


class RoutingService:
    @staticmethod
    async def validate(db, routes):
        connections, models, versions, accounts, credentials, key_versions = await RoutingDao.dependencies(db, routes)
        connections = {row.connection_id: row for row in connections}
        models = {row.model_id: row for row in models}
        accounts = {row.account_id: row for row in accounts}
        credentials = {row.credential_id: row for row in credentials}
        fail = WorkspaceService.conflict
        now = TimezoneUtil.utc_now()
        for route in routes:
            model, account = models.get(int(route.model_id)), accounts.get(int(route.account_id))
            if model is None or account is None or model.connection_id != account.connection_id:
                fail('ROUTE_SCOPE_MISMATCH', '模型和账号必须存在且属于同一供应商连接')
            connection = connections.get(account.connection_id)
            if connection is None:
                fail('ROUTE_SCOPE_MISMATCH', '供应商连接不存在')
            matching = [
                version
                for version in versions
                if version.model_id == model.model_id and version.region == account.region
            ]
            if not matching:
                fail('ROUTE_REGION_MISMATCH', '模型没有与账号区域匹配的能力版本')
            if route.enabled and (
                connection.status != '1'
                or account.status != '0'
                or not any(version.status == '2' for version in matching)
            ):
                fail('ROUTE_NOT_READY', '启用路由需要已启用连接、正常账号和同区域已发布模型能力')
            for candidate in route.credentials:
                credential = credentials.get(int(candidate.credential_id))
                if credential is None or credential.account_id != account.account_id:
                    fail('ROUTE_CREDENTIAL_MISMATCH', '候选凭据必须属于路由指定账号')
                if route.enabled and (
                    credential.status != '1'
                    or not any(
                        version.credential_id == credential.credential_id
                        and version.state == '1'
                        and version.connection_version_id == connection.current_version_id
                        and version.valid_from <= now
                        and (version.valid_until is None or now < version.valid_until)
                        for version in key_versions
                    )
                ):
                    fail('ROUTE_CREDENTIAL_NOT_READY', '候选凭据缺少当前连接配置下有效且已启用的版本')

    @classmethod
    async def save(cls, db, user, project_id, payload, key):
        path, prefix = f'/project-provider-configs/{project_id}', '/api/admin/v1'
        data = payload.model_dump(by_alias=True)
        try:
            await AdminScopeService.project(db, user, project_id, 'provider:route', write=True)
            await WriteService.lock(db, user, path, key, api_prefix=prefix)
            group = await RoutingDao.group(db, project_id, lock=True)
            if group is None:
                WorkspaceService.conflict('ROUTING_SET_MISSING', '项目路由组缺失，请执行迁移')
            replay = await WriteService.replay(db, user, path, key, data, 'PUT', api_prefix=prefix)
            if replay:
                await db.commit()
                return replay, True
            WorkspaceService.check_revision(group, payload.revision)
            await cls.validate(db, payload.routes)
            before = await cls.result(db, group)
            audit = WriteService.audit(user)
            group.revision += 1
            group.update_by, group.update_time = audit['update_by'], audit['update_time']
            await RoutingDao.replace(db, project_id, payload.routes, group.revision, audit)
            after = await cls.result(db, group)
            await ProviderDao.add(
                db,
                HfAuditLog,
                actor_id=user.user.user_id,
                actor_kind='user',
                project_id=project_id,
                object_type='project_routing_set',
                object_id=str(group.routing_set_id),
                action='replace',
                request_id=WriteService.digest({'path': path, 'key': key}),
                before_after={'before': before, 'after': after},
                **audit,
            )
            return await WriteService.finish(
                db, user, path, key, data, after, 'project_routing_set', group.routing_set_id, 'PUT', api_prefix=prefix
            )
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    async def result(db, group):
        routes, policies = await RoutingDao.rows(db, group.project_id)
        candidates = {row.config_id: [] for row in routes}
        for policy in policies:
            candidates[policy.project_provider_config_id].append(
                {
                    'credentialId': str(policy.credential_id),
                    'priority': policy.priority,
                    'maxConcurrency': policy.max_concurrency,
                }
            )
        return {
            'projectId': str(group.project_id),
            'revision': str(group.revision),
            'routes': [
                {
                    'modelId': str(row.model_id),
                    'accountId': str(row.account_id),
                    'priority': row.priority,
                    'enabled': row.status == '0',
                    'credentials': candidates[row.config_id],
                }
                for row in routes
            ],
        }

    @classmethod
    async def get(cls, db, user, project_id):
        await AdminScopeService.project(db, user, project_id, 'provider:route')
        # 读取也锁聚合行，保证多次查询不会混入并发整组替换的不同版本。
        group = await RoutingDao.group(db, project_id, lock=True)
        if group is None:
            WorkspaceService.conflict('ROUTING_SET_MISSING', '项目路由组缺失，请执行迁移或联系管理员')
        return await cls.result(db, group)
