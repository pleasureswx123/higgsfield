"""按素材版本、账号和原凭据隔离上传复用；事务锁覆盖准备阶段。"""

import hashlib
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from module_higgsfield.entity.do.provider_upload_do import HfProviderUpload


class ProviderUploadDao:
    @staticmethod
    async def unresolved(
        db: AsyncSession, asset_version_id: int, account_id: int, credential_version_id: int
    ) -> HfProviderUpload | None:
        return await db.scalar(
            select(HfProviderUpload)
            .where(
                HfProviderUpload.asset_version_id == asset_version_id,
                HfProviderUpload.account_id == account_id,
                HfProviderUpload.credential_version_id == credential_version_id,
                HfProviderUpload.state.in_(('0', '3')),
            )
            .order_by(HfProviderUpload.provider_upload_id)
            .limit(1)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    @staticmethod
    async def lock_scope(db: AsyncSession, asset_version_id: int, account_id: int, credential_version_id: int) -> None:
        identity = f'hf:provider-upload:{asset_version_id}:{account_id}:{credential_version_id}'.encode('ascii')
        lock_id = int.from_bytes(hashlib.sha256(identity).digest()[:8], 'big', signed=True)
        await db.execute(text('SELECT pg_advisory_xact_lock(:identity)'), {'identity': lock_id})

    @staticmethod
    async def reusable(
        db: AsyncSession, asset_version_id: int, account_id: int, credential_version_id: int, required_until: datetime
    ) -> HfProviderUpload | None:
        return await db.scalar(
            select(HfProviderUpload)
            .where(
                HfProviderUpload.asset_version_id == asset_version_id,
                HfProviderUpload.account_id == account_id,
                HfProviderUpload.credential_version_id == credential_version_id,
                HfProviderUpload.state == '1',
                HfProviderUpload.expires_time > required_until,
            )
            .order_by(HfProviderUpload.expires_time.desc(), HfProviderUpload.provider_upload_id.desc())
            .limit(1)
        )

    @staticmethod
    async def locked(db: AsyncSession, identity: int) -> HfProviderUpload | None:
        return await db.scalar(
            select(HfProviderUpload)
            .where(HfProviderUpload.provider_upload_id == identity)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    @staticmethod
    async def add(db: AsyncSession, values: dict) -> HfProviderUpload:
        row = HfProviderUpload(**values)
        db.add(row)
        await db.flush()
        return row
