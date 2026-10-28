from hashlib import sha256
from sqlalchemy import select, func, text
from module_higgsfield.entity.do.model_do import HfProviderConnection
from module_higgsfield.entity.do.provider_do import HfProviderConnectionVersion, HfProviderAccount


class ProviderDao:
    @staticmethod
    async def account_exists(db, payload):
        return await db.scalar(
            select(HfProviderAccount.account_id).where(
                HfProviderAccount.connection_id == int(payload.connection_id),
                HfProviderAccount.account_code == payload.account_code,
                HfProviderAccount.region == payload.region,
                HfProviderAccount.upstream_project == payload.upstream_project,
            )
        )

    @staticmethod
    async def accounts(db, query):
        statement = select(HfProviderAccount)
        if query.account_id:
            statement = statement.where(HfProviderAccount.account_id == int(query.account_id))
        if query.connection_id:
            statement = statement.where(HfProviderAccount.connection_id == int(query.connection_id))
        if query.region:
            statement = statement.where(HfProviderAccount.region == query.region)
        total = await db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = (
            await db.scalars(
                statement.order_by(HfProviderAccount.account_id.desc())
                .offset((query.page_num - 1) * query.page_size)
                .limit(query.page_size)
            )
        ).all()
        return rows, total

    @staticmethod
    async def connection(db, connection_id, lock=False):
        query = (
            select(HfProviderConnection)
            .where(HfProviderConnection.connection_id == connection_id)
            .execution_options(populate_existing=True)
        )
        return await db.scalar(query.with_for_update() if lock else query)

    @staticmethod
    async def version(db, version_id):
        return await db.get(HfProviderConnectionVersion, version_id) if version_id else None

    @staticmethod
    async def unique_name(db, environment, name, excluding=None):
        token = int.from_bytes(sha256(f'provider:{environment}:{name}'.encode()).digest()[:8], signed=True)
        await db.execute(text('SELECT pg_advisory_xact_lock(:token)'), {'token': token})
        query = select(HfProviderConnection.connection_id).where(
            HfProviderConnection.environment == environment, HfProviderConnection.connection_name == name
        )
        if excluding is not None:
            query = query.where(HfProviderConnection.connection_id != excluding)
        return await db.scalar(query)

    @staticmethod
    async def page(db, query):
        statement = select(HfProviderConnection)
        if query.environment:
            statement = statement.where(HfProviderConnection.environment == query.environment)
        if query.status:
            statement = statement.where(
                HfProviderConnection.status == {'draft': '0', 'active': '1', 'disabled': '2'}[query.status]
            )
        total = await db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = (
            await db.scalars(
                statement.order_by(HfProviderConnection.connection_id.desc())
                .offset((query.page_num - 1) * query.page_size)
                .limit(query.page_size)
            )
        ).all()
        return rows, total

    @staticmethod
    async def add(db, model, **values):
        row = model(**values)
        db.add(row)
        await db.flush()
        return row
