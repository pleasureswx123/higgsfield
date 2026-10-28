"""整组路由查询与聚合锁。"""

from sqlalchemy import select, delete
from module_higgsfield.entity.do.model_do import HfProviderConnection, HfModelProfile, HfModelProfileVersion
from module_higgsfield.entity.do.provider_do import HfProviderAccount
from module_higgsfield.entity.do.credential_do import HfProviderCredential, HfCredentialVersion
from module_higgsfield.entity.do.routing_do import HfProjectRoutingSet, HfProjectProviderConfig, HfRoutingPolicy


class RoutingDao:
    @staticmethod
    async def dependencies(db, routes):
        model_ids = sorted({int(row.model_id) for row in routes})
        account_ids = sorted({int(row.account_id) for row in routes})
        credential_ids = sorted({int(item.credential_id) for row in routes for item in row.credentials})
        models = (await db.scalars(select(HfModelProfile).where(HfModelProfile.model_id.in_(model_ids)))).all()
        accounts = (
            await db.scalars(select(HfProviderAccount).where(HfProviderAccount.account_id.in_(account_ids)))
        ).all()
        connection_ids = sorted({row.connection_id for row in [*models, *accounts]})

        async def locked(model, column, ids):
            return (
                await db.scalars(
                    select(model)
                    .where(column.in_(ids))
                    .order_by(column)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            ).all()

        connections = await locked(HfProviderConnection, HfProviderConnection.connection_id, connection_ids)
        models = await locked(HfModelProfile, HfModelProfile.model_id, model_ids)
        versions = (
            await db.scalars(
                select(HfModelProfileVersion)
                .where(HfModelProfileVersion.model_id.in_(model_ids))
                .order_by(HfModelProfileVersion.model_version_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).all()
        accounts = await locked(HfProviderAccount, HfProviderAccount.account_id, account_ids)
        credentials = await locked(HfProviderCredential, HfProviderCredential.credential_id, credential_ids)
        # 路由校验只读取密钥元数据，不加载密文、随机数或内部指纹。
        key_versions = (
            await db.execute(
                select(
                    HfCredentialVersion.credential_version_id,
                    HfCredentialVersion.version_no,
                    HfCredentialVersion.credential_id,
                    HfCredentialVersion.connection_version_id,
                    HfCredentialVersion.state,
                    HfCredentialVersion.valid_from,
                    HfCredentialVersion.valid_until,
                )
                .where(HfCredentialVersion.credential_id.in_(credential_ids))
                .order_by(HfCredentialVersion.credential_version_id)
                .with_for_update()
            )
        ).all()
        return connections, models, versions, accounts, credentials, key_versions

    @staticmethod
    async def replace(db, project_id, routes, revision, audit):
        ids = select(HfProjectProviderConfig.config_id).where(HfProjectProviderConfig.project_id == project_id)
        await db.execute(delete(HfRoutingPolicy).where(HfRoutingPolicy.project_provider_config_id.in_(ids)))
        await db.execute(delete(HfProjectProviderConfig).where(HfProjectProviderConfig.project_id == project_id))
        for item in routes:
            row = HfProjectProviderConfig(
                project_id=project_id,
                model_id=int(item.model_id),
                account_id=int(item.account_id),
                status='0' if item.enabled else '1',
                priority=item.priority,
                revision=revision,
                **audit,
            )
            db.add(row)
            await db.flush()
            db.add_all(
                [
                    HfRoutingPolicy(
                        project_provider_config_id=row.config_id,
                        credential_id=int(candidate.credential_id),
                        priority=candidate.priority,
                        max_concurrency=candidate.max_concurrency,
                        enabled='Y' if item.enabled else 'N',
                        **audit,
                    )
                    for candidate in item.credentials
                ]
            )
        await db.flush()

    @staticmethod
    async def group(db, project_id, lock=False):
        statement = (
            select(HfProjectRoutingSet)
            .where(HfProjectRoutingSet.project_id == project_id)
            .execution_options(populate_existing=True)
        )
        return await db.scalar(statement.with_for_update() if lock else statement)

    @staticmethod
    async def rows(db, project_id):
        routes = (
            await db.scalars(
                select(HfProjectProviderConfig)
                .where(HfProjectProviderConfig.project_id == project_id)
                .order_by(HfProjectProviderConfig.priority, HfProjectProviderConfig.config_id)
            )
        ).all()
        if not routes:
            return routes, []
        policies = (
            await db.scalars(
                select(HfRoutingPolicy)
                .where(HfRoutingPolicy.project_provider_config_id.in_([row.config_id for row in routes]))
                .order_by(HfRoutingPolicy.priority, HfRoutingPolicy.policy_id)
            )
        ).all()
        return routes, policies
