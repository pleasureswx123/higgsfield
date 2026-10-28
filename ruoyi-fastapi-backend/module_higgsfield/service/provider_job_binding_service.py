"""发送和查询共用原任务的固定凭据校验，不自动替换账号或Key。"""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from module_higgsfield.dao.credential_dao import CredentialDao
from module_higgsfield.dao.provider_dao import ProviderDao
from module_higgsfield.entity.do.credential_do import HfCredentialVersion
from module_higgsfield.entity.do.job_do import HfCreationJob
from module_higgsfield.entity.do.provider_do import HfProviderAccount, HfProviderConnectionVersion
from module_higgsfield.service.job_lease_service import JobLease, JobLeaseService
from module_higgsfield.service.project_workspace_service import WorkspaceService


class ProviderJobBindingService:
    @staticmethod
    async def require(
        db: AsyncSession, lease: JobLease, job: HfCreationJob
    ) -> tuple[HfCreationJob, datetime, HfProviderAccount, HfCredentialVersion, HfProviderConnectionVersion]:
        route = job.input_snapshot.get('route', {})
        version = await CredentialDao.version(db, job.credential_version_id)
        credential = await CredentialDao.get(db, version.credential_id) if version else None
        account = await CredentialDao.account(db, credential.account_id) if credential else None
        if account is None or str(account.account_id) != route.get('accountId'):
            WorkspaceService.conflict('PROVIDER_BINDING_INVALID', '原任务凭据及账号绑定不完整')
        connection = await ProviderDao.connection(db, account.connection_id, lock=True)
        account = await CredentialDao.account(db, account.account_id, lock=True)
        credential = await CredentialDao.get(db, credential.credential_id, lock=True)
        version = await CredentialDao.version(db, job.credential_version_id, lock=True)
        config = await ProviderDao.version(db, version.connection_version_id)
        # 等待连接或凭据锁可能跨过有效期，写发送意图前重新核对租约和数据库时钟。
        job, now = await JobLeaseService.guard(db, lease)
        if (
            connection is None
            or connection.status != '1'
            or account.status != '0'
            or credential.status not in {'1', '2'}
            or version.state not in {'1', '2'}
            or version.valid_from > now
            or (version.valid_until is not None and version.valid_until <= now)
            or str(version.connection_version_id) != route.get('connectionVersionId')
            or config is None
            or config.connection_id != connection.connection_id
        ):
            WorkspaceService.conflict(
                'PROVIDER_CREDENTIAL_UNAVAILABLE', '原任务凭据或连接已不可用于发送，不自动切换凭据'
            )
        return job, now, account, version, config
