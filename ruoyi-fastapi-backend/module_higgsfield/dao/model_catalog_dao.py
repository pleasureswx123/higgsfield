"""项目显式路由过滤在分页之前完成，不加载供应商秘密。"""

from sqlalchemy import select, exists, func, or_
from module_higgsfield.entity.do.model_do import (
    HfModelProfile as Model,
    HfModelProfileVersion as Version,
    HfModelVariant as Variant,
)
from module_higgsfield.entity.do.routing_do import HfProjectProviderConfig as Route
from module_higgsfield.entity.do.provider_do import HfProviderAccount as Account


class ModelCatalogDao:
    @staticmethod
    def authorized(project_id):
        return exists(
            select(Route.config_id)
            .join(Account, Account.account_id == Route.account_id)
            .where(
                Route.project_id == project_id,
                Route.model_id == Model.model_id,
                Route.status == '0',
                Account.connection_id == Model.connection_id,
                Account.region == Version.region,
            )
        )

    @classmethod
    async def page(cls, db, query):
        statement = (
            select(Model, Version)
            .join(Version, Version.model_id == Model.model_id)
            .where(Version.status == '2', Model.kind == query.kind, cls.authorized(int(query.project_id)))
        )
        if query.version_id:
            statement = statement.where(Version.model_version_id == int(query.version_id))
        if query.q.strip():
            value = query.q.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            statement = statement.where(
                or_(Model.display_name.ilike(f'%{value}%', escape='\\'), Model.code.ilike(f'%{value}%', escape='\\'))
            )
        total = await db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = (
            await db.execute(
                statement.order_by(Model.model_id, Version.version_no.desc())
                .offset((query.page_num - 1) * query.page_size)
                .limit(query.page_size)
            )
        ).all()
        ids = [version.model_version_id for _, version in rows]
        variants = (
            (
                await db.scalars(select(Variant).where(Variant.model_version_id.in_(ids)).order_by(Variant.variant_id))
            ).all()
            if ids
            else []
        )
        return rows, variants, total

    @classmethod
    async def version(cls, db, project_id, version_id):
        return (
            await db.execute(
                select(Model, Version)
                .join(Version, Version.model_id == Model.model_id)
                .where(Version.model_version_id == version_id, Version.status == '2', cls.authorized(project_id))
                .with_for_update(of=Version)
            )
        ).first()
