"""凭据草稿登记与轮换；不因保存密钥而自动启用供应商。"""

from dataclasses import asdict
from common.vo import PageModel
from exceptions.exception import PermissionException, ServiceWarning
from module_higgsfield.dao.credential_dao import CredentialDao
from module_higgsfield.dao.provider_dao import ProviderDao
from module_higgsfield.dao.project_workspace_dao import WorkspaceDao
from module_higgsfield.entity.do.credential_do import HfProviderCredential, HfCredentialVersion
from module_higgsfield.entity.do.audit_do import HfAuditLog
from module_higgsfield.service.credential_crypto_service import CredentialCryptoService
from module_higgsfield.service.provider_service import ProviderService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService
from utils.time_util import TimezoneUtil


class CredentialService:
    states = dict(zip('01234', ('draft', 'active', 'draining', 'disabled', 'revoked')))
    fail = staticmethod(WorkspaceService.conflict)
    require = staticmethod(ProviderService.require)

    @classmethod
    def result(cls, row):
        return dict(
            id=str(row.credential_id),
            accountId=str(row.account_id),
            name=row.credential_name,
            ownerId=str(row.owner_id),
            status=cls.states[row.status],
            revision=str(row.revision),
        )

    @classmethod
    def version_result(cls, row, in_flight=0):
        return dict(
            id=str(row.credential_version_id),
            credentialId=str(row.credential_id),
            versionNo=row.version_no,
            connectionVersionId=str(row.connection_version_id),
            state=cls.states[row.state],
            maskedSuffix=row.masked_suffix,
            validFrom=row.valid_from,
            validUntil=row.valid_until,
            revision=str(row.revision),
            inFlightCount=str(in_flight),
        )

    @classmethod
    async def identities(cls, db, rows):
        results = {row.credential_id: {**cls.result(row), 'versionsSummary': []} for row in rows}
        versions = await CredentialDao.summaries(db, list(results))
        counts = await CredentialDao.in_flight(db, [version.credential_version_id for version in versions])
        for version in versions:
            results[version.credential_id]['versionsSummary'].append(
                dict(
                    id=str(version.credential_version_id),
                    state=cls.states[version.state],
                    maskedSuffix=version.masked_suffix,
                    validUntil=version.valid_until,
                    inFlightCount=str(counts.get(version.credential_version_id, 0)),
                )
            )
        return list(results.values())

    @classmethod
    async def get(cls, db, user, credential_id):
        cls.require(user, 'credential:read')
        row = await CredentialDao.get(db, credential_id)
        if row is None:
            cls.fail('RESOURCE_NOT_FOUND', '凭据不存在')
        return (await cls.identities(db, [row]))[0]

    @classmethod
    async def listing(cls, db, user, query, credential_id=None):
        cls.require(user, 'credential:read')
        if credential_id is not None:
            await cls.get(db, user, credential_id)
        rows, total = await CredentialDao.page(db, query, credential_id)
        if credential_id is None:
            values = await cls.identities(db, rows)
        else:
            counts = await CredentialDao.in_flight(db, [row.credential_version_id for row in rows])
            values = [cls.version_result(row, counts.get(row.credential_version_id, 0)) for row in rows]
        return PageModel(
            rows=values,
            total=total,
            pageNum=query.page_num,
            pageSize=query.page_size,
            hasNext=query.page_num * query.page_size < total,
        )

    @classmethod
    async def save(cls, db, user, payload, key, credential_id=None, crypto=None):
        cls.require(user, 'credential:write' if credential_id is None else 'credential:rotate')
        path = '/credentials' if credential_id is None else f'/credentials/{credential_id}/versions'
        prefix = '/api/admin/v1'
        try:
            crypto = crypto or CredentialCryptoService()
            # 幂等摘要只接收带密钥指纹，不接收原文或可离线猜测的普通摘要。
            data = payload.model_dump(mode='json', by_alias=True)
            data['secretFingerprint'] = crypto.fingerprint(payload.api_key.get_secret_value())
            await WriteService.lock(db, user, path, key, api_prefix=prefix)
            identity = await CredentialDao.get(db, credential_id) if credential_id is not None else None
            if credential_id is not None and identity is None:
                cls.fail('RESOURCE_NOT_FOUND', '凭据不存在')
            account_id = identity.account_id if identity else int(payload.account_id)
            account = await CredentialDao.account(db, account_id)
            if account is None:
                cls.fail('RESOURCE_NOT_FOUND', '供应商账号不存在')
            # 固定锁序：连接、账号、凭据。配置与状态变更也必须遵守此顺序。
            connection = await ProviderDao.connection(db, account.connection_id, lock=True)
            account = await CredentialDao.account(db, account_id, lock=True)
            row = await CredentialDao.get(db, credential_id, lock=True) if identity else None
            replay = await WriteService.replay(db, user, path, key, data, api_prefix=prefix)
            if replay:
                await db.commit()
                return replay, True
            if connection is None or connection.status == '2' or account.status != '0':
                cls.fail('PROVIDER_DISABLED', '连接或供应商账号不可用')
            version = await ProviderDao.version(db, int(payload.connection_version_id))
            if version is None or version.connection_id != account.connection_id:
                cls.fail('CONNECTION_VERSION_MISMATCH', '连接配置版本不属于此供应商账号')
            if payload.valid_until is not None and payload.valid_until <= TimezoneUtil.utc_now():
                cls.fail('CREDENTIAL_EXPIRED', '不能登记已经过期的凭据版本')
            audit = WriteService.audit(user)
            if row is None:
                owner = await WorkspaceDao.user(db, int(payload.owner_id), lock=True)
                if owner is None or owner['status'] != '0' or owner['del_flag'] != '0':
                    cls.fail('CREDENTIAL_OWNER_INVALID', '凭据责任人不存在或已停用')
                if await CredentialDao.name_exists(db, account_id, payload.name):
                    cls.fail('CREDENTIAL_NAME_EXISTS', '此账号下已存在同名凭据')
                row = await ProviderDao.add(
                    db,
                    HfProviderCredential,
                    account_id=account_id,
                    credential_name=payload.name,
                    owner_id=int(payload.owner_id),
                    status='0',
                    revision=1,
                    **audit,
                )
            else:
                WorkspaceService.check_revision(row, payload.revision)
                if row.status in ('3', '4'):
                    cls.fail('CREDENTIAL_DISABLED', '已停用或撤销的凭据不能增加版本')
                row.revision += 1
                row.update_by, row.update_time = audit['update_by'], audit['update_time']
            number = await CredentialDao.next_version(db, row.credential_id)
            encrypted = crypto.encrypt(
                payload.api_key.get_secret_value(), row.credential_id, version.connection_version_id, number
            )
            saved = await ProviderDao.add(
                db,
                HfCredentialVersion,
                credential_id=row.credential_id,
                connection_version_id=version.connection_version_id,
                version_no=number,
                state='0',
                revision=1,
                valid_from=payload.valid_from,
                valid_until=payload.valid_until,
                **asdict(encrypted),
                **audit,
            )
            await ProviderDao.add(
                db,
                HfAuditLog,
                actor_id=user.user.user_id,
                actor_kind='user',
                object_type='credential',
                object_id=str(row.credential_id),
                action='create' if credential_id is None else 'rotate',
                request_id=WriteService.digest({'path': path, 'key': key}),
                before_after={
                    'versionId': str(saved.credential_version_id),
                    'versionNo': number,
                    'connectionVersionId': str(version.connection_version_id),
                    'state': 'draft',
                },
                **audit,
            )
            result = (await cls.identities(db, [row]))[0] if credential_id is None else cls.version_result(saved)
            return await WriteService.finish(
                db, user, path, key, data, result, 'credential', row.credential_id, api_prefix=prefix
            )
        except (ServiceWarning, PermissionException):
            await db.rollback()
            raise
        except Exception:
            await db.rollback()
            # 不让驱动异常参数、供应商输入或异常上下文进入通用操作日志。
            raise ServiceWarning(
                message='凭据保存失败，请联系管理员核查', data={'errorCode': 'CREDENTIAL_SAVE_FAILED'}
            ) from None
