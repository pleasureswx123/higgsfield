"""凭据数据库操作；版本列表只选择可公开的元数据列。"""

from sqlalchemy import select, func, or_
from module_higgsfield.entity.do.credential_do import HfProviderCredential as Credential, HfCredentialVersion as Version
from module_higgsfield.entity.do.provider_do import HfProviderAccount
from module_higgsfield.entity.do.job_do import HfCreationJob


class CredentialDao:
    @staticmethod
    async def version(db, identity, lock=False):
        statement = select(Version).where(Version.credential_version_id == int(identity))
        return await db.scalar(
            statement.with_for_update().execution_options(populate_existing=True) if lock else statement
        )

    @staticmethod
    async def version_states(db, credential_id):
        await db.flush()
        return (await db.scalars(select(Version.state).where(Version.credential_id == credential_id))).all()

    @staticmethod
    async def in_flight(db, version_ids):
        if not version_ids:
            return {}
        # 编排未结束，或上游仍排队、运行、未知的任务，仍依赖原始凭据。
        rows = await db.execute(
            select(HfCreationJob.credential_version_id, func.count())
            .where(
                HfCreationJob.credential_version_id.in_(version_ids),
                or_(HfCreationJob.orchestration_state != '5', HfCreationJob.upstream_state.in_(('1', '2', '6'))),
            )
            .group_by(HfCreationJob.credential_version_id)
        )
        return dict(rows.all())

    @staticmethod
    async def summaries(db, credential_ids):
        if not credential_ids:
            return []
        return (
            await db.execute(
                select(
                    Version.credential_id,
                    Version.credential_version_id,
                    Version.state,
                    Version.masked_suffix,
                    Version.valid_until,
                )
                .where(Version.credential_id.in_(credential_ids))
                .order_by(Version.version_no.desc())
            )
        ).all()

    @staticmethod
    async def get(db, credential_id, lock=False):
        query = (
            select(Credential)
            .where(Credential.credential_id == credential_id)
            .execution_options(populate_existing=True)
        )
        return await db.scalar(query.with_for_update() if lock else query)

    @staticmethod
    async def account(db, account_id, lock=False):
        query = (
            select(HfProviderAccount)
            .where(HfProviderAccount.account_id == account_id)
            .execution_options(populate_existing=True)
        )
        return await db.scalar(query.with_for_update() if lock else query)

    @staticmethod
    async def name_exists(db, account_id, name):
        return await db.scalar(
            select(Credential.credential_id).where(
                Credential.account_id == account_id, Credential.credential_name == name
            )
        )

    @staticmethod
    async def next_version(db, credential_id):
        return (
            await db.scalar(select(func.max(Version.version_no)).where(Version.credential_id == credential_id)) or 0
        ) + 1

    @staticmethod
    async def page(db, query, credential_id=None):
        if credential_id is None:
            statement = select(Credential)
            if query.account_id:
                statement = statement.where(Credential.account_id == int(query.account_id))
            if query.status:
                state = dict(zip(('draft', 'active', 'draining', 'disabled', 'revoked'), '01234'))[query.status]
                statement = statement.where(Credential.status == state)
            order = Credential.credential_id
        else:
            statement = select(
                Version.credential_version_id,
                Version.credential_id,
                Version.version_no,
                Version.connection_version_id,
                Version.state,
                Version.masked_suffix,
                Version.valid_from,
                Version.valid_until,
                Version.revision,
            ).where(Version.credential_id == credential_id)
            order = Version.version_no
        total = await db.scalar(select(func.count()).select_from(statement.subquery()))
        result = await db.execute(
            statement.order_by(order.desc()).offset((query.page_num - 1) * query.page_size).limit(query.page_size)
        )
        return (result.scalars().all() if credential_id is None else result.all()), total
