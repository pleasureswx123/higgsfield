"""受理事务锁定显式路由与可用凭据；不解密密钥、不提交事务。"""

from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession

from module_admin.entity.vo.user_vo import CurrentUserModel
from module_higgsfield.dao.credential_dao import CredentialDao
from module_higgsfield.dao.job_lease_dao import JobLeaseDao
from module_higgsfield.dao.provider_dao import ProviderDao
from module_higgsfield.dao.routing_dao import RoutingDao
from module_higgsfield.service.project_workspace_service import WorkspaceService


class GenerationRouteService:
    @classmethod
    async def select(cls, db: AsyncSession, user: CurrentUserModel, project_id: int, version_id: int) -> dict:
        """必须在输入准备前调用；调用方在同一事务持锁写入任务后才可提交。"""
        await WorkspaceService.authorize(db, user, project_id, 'generation:create', write=True)
        group = await RoutingDao.group(db, project_id, lock=True)
        if group is None:
            WorkspaceService.conflict('GENERATION_ROUTE_UNAVAILABLE', '项目尚未配置生成路由')
        routes, policies = await RoutingDao.rows(db, project_id)
        active = [row for row in routes if row.status == '0']
        candidates = [row for row in policies if row.enabled == 'Y']
        # 与整组配置更新采用相同锁顺序：路由组→连接→模型→能力版本→账号→凭据→密钥版本。
        definitions = [
            SimpleNamespace(
                model_id=route.model_id,
                account_id=route.account_id,
                credentials=[item for item in candidates if item.project_provider_config_id == route.config_id],
            )
            for route in active
        ]
        connections, models, versions, accounts, credentials, keys = await RoutingDao.dependencies(db, definitions)
        model_version = next(
            (row for row in versions if row.model_version_id == version_id and row.status == '2'), None
        )
        if model_version is None:
            WorkspaceService.conflict('GENERATION_ROUTE_UNAVAILABLE', '模型版本没有可用项目路由')
        model = next(row for row in models if row.model_id == model_version.model_id)
        connection = next(
            (row for row in connections if row.connection_id == model.connection_id and row.status == '1'), None
        )
        if connection is None or connection.current_version_id is None:
            WorkspaceService.conflict('GENERATION_ROUTE_UNAVAILABLE', '模型连接当前不可用')
        config = await ProviderDao.version(db, connection.current_version_id)
        if config is None or config.connection_id != connection.connection_id:
            WorkspaceService.conflict('GENERATION_ROUTE_UNAVAILABLE', '连接固定配置版本缺失或不属于此连接')
        account_map = {row.account_id: row for row in accounts}
        credential_map = {row.credential_id: row for row in credentials}
        counts = await CredentialDao.in_flight(db, [row.credential_version_id for row in keys])
        now = await JobLeaseDao.now(db)
        for route in active:
            account = account_map.get(route.account_id)
            if (
                route.model_id != model.model_id
                or account is None
                or account.status != '0'
                or account.connection_id != connection.connection_id
                or account.region != model_version.region
            ):
                continue
            for policy in sorted(
                (item for item in candidates if item.project_provider_config_id == route.config_id),
                key=lambda item: (item.priority, item.policy_id),
            ):
                credential = credential_map.get(policy.credential_id)
                if credential is None or credential.account_id != account.account_id or credential.status != '1':
                    continue
                identity_keys = [item for item in keys if item.credential_id == credential.credential_id]
                # 轮换不能重置同一身份的并发占用；排空版本上的未知任务仍计入。
                if sum(counts.get(item.credential_version_id, 0) for item in identity_keys) >= policy.max_concurrency:
                    continue
                eligible = [
                    item
                    for item in identity_keys
                    if item.state == '1'
                    and item.connection_version_id == connection.current_version_id
                    and item.valid_from <= now
                    and (item.valid_until is None or now < item.valid_until)
                ]
                if not eligible:
                    continue
                selected = max(eligible, key=lambda item: (item.version_no, item.credential_version_id))
                return {
                    'routingRevision': str(group.revision),
                    'routeId': str(route.config_id),
                    'policyId': str(policy.policy_id),
                    'accountId': str(account.account_id),
                    'credentialVersionId': str(selected.credential_version_id),
                    'connectionVersionId': str(selected.connection_version_id),
                    'region': account.region,
                    'upstreamProject': account.upstream_project,
                }
        WorkspaceService.conflict('GENERATION_ROUTE_UNAVAILABLE', '当前没有有效且有并发容量的候选凭据')
        return None
