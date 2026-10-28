"""供应商连接登记与配置版本管理，不执行网络探测或激活。"""

from pydantic import ValidationError
from common.vo import PageModel
from exceptions.exception import PermissionException
from module_higgsfield.dao.provider_dao import ProviderDao
from module_higgsfield.entity.do.model_do import HfProviderConnection
from module_higgsfield.entity.do.provider_do import HfProviderConnectionVersion, HfProviderAccount
from module_higgsfield.entity.vo.provider_vo import ConnectionFields
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService


class ProviderService:
    fail = staticmethod(WorkspaceService.conflict)

    @staticmethod
    def account_result(row):
        return {
            'id': str(row.account_id),
            'connectionId': str(row.connection_id),
            'accountCode': row.account_code,
            'region': row.region,
            'upstreamProject': row.upstream_project,
            'status': 'active' if row.status == '0' else 'disabled',
        }

    @classmethod
    async def accounts(cls, db, user, query):
        cls.require(user, 'provider:read')
        rows, total = await ProviderDao.accounts(db, query)
        return PageModel(
            rows=[cls.account_result(row) for row in rows],
            total=total,
            pageNum=query.page_num,
            pageSize=query.page_size,
            hasNext=query.page_num * query.page_size < total,
        )

    @classmethod
    async def create_account(cls, db, user, payload, key):
        cls.require(user, 'provider:write')
        path, prefix = '/provider-accounts', '/api/admin/v1'
        data = payload.model_dump(by_alias=True)
        try:
            await WriteService.lock(db, user, path, key, api_prefix=prefix)
            connection = await ProviderDao.connection(db, int(payload.connection_id), lock=True)
            if connection is None:
                cls.fail('RESOURCE_NOT_FOUND', '供应商连接不存在')
            replay = await WriteService.replay(db, user, path, key, data, api_prefix=prefix)
            if replay:
                await db.commit()
                return replay, True
            if connection.status == '2':
                cls.fail('CONNECTION_DISABLED', '已停用连接不能登记新账号')
            if await ProviderDao.account_exists(db, payload):
                cls.fail('PROVIDER_ACCOUNT_EXISTS', '相同连接、账号、区域和上游项目已登记')
            row = await ProviderDao.add(
                db,
                HfProviderAccount,
                connection_id=int(payload.connection_id),
                account_code=payload.account_code,
                region=payload.region,
                upstream_project=payload.upstream_project,
                status='0',
                **WriteService.audit(user),
            )
            return await WriteService.finish(
                db,
                user,
                path,
                key,
                data,
                cls.account_result(row),
                'provider_account',
                row.account_id,
                api_prefix=prefix,
            )
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    def require(user, permission):
        if '*:*:*' not in user.permissions and permission not in user.permissions:
            raise PermissionException(message='没有执行供应商配置操作的权限')

    @staticmethod
    async def result(db, row):
        version = await ProviderDao.version(db, row.current_version_id)
        return {
            'id': str(row.connection_id),
            'name': row.connection_name,
            'environment': row.environment,
            'status': {'0': 'draft', '1': 'active', '2': 'disabled'}[row.status],
            'revision': str(row.revision),
            'currentVersion': {
                'id': str(version.connection_version_id),
                'versionNo': version.version_no,
                'baseUrl': version.base_url,
                'adapterVersion': version.adapter_version,
                'config': version.config,
                'configHash': version.config_hash,
            }
            if version
            else None,
        }

    @classmethod
    async def get(cls, db, user, connection_id):
        cls.require(user, 'provider:read')
        row = await ProviderDao.connection(db, connection_id)
        if row is None:
            cls.fail('RESOURCE_NOT_FOUND', '供应商连接不存在')
        return await cls.result(db, row)

    @classmethod
    async def listing(cls, db, user, query):
        cls.require(user, 'provider:read')
        rows, total = await ProviderDao.page(db, query)
        return PageModel(
            rows=[await cls.result(db, row) for row in rows],
            total=total,
            pageNum=query.page_num,
            pageSize=query.page_size,
            hasNext=query.page_num * query.page_size < total,
        )

    @classmethod
    async def save(cls, db, user, payload, key, connection_id=None):
        cls.require(user, 'provider:write')
        path = '/provider-connections' + (f'/{connection_id}' if connection_id is not None else '')
        method = 'POST' if connection_id is None else 'PATCH'
        data = payload.model_dump(by_alias=True, exclude_unset=True)
        try:
            await WriteService.lock(db, user, path, key, api_prefix='/api/admin/v1')
            row = await ProviderDao.connection(db, connection_id, lock=True) if connection_id is not None else None
            if connection_id is not None and row is None:
                cls.fail('RESOURCE_NOT_FOUND', '供应商连接不存在')
            replay = await WriteService.replay(db, user, path, key, data, method, api_prefix='/api/admin/v1')
            if replay:
                await db.commit()
                return replay, True
            previous = await ProviderDao.version(db, row.current_version_id) if row else None
            if row:
                WorkspaceService.check_revision(row, payload.revision)
                if previous is None:
                    cls.fail('CONNECTION_CONFIG_MISSING', '连接配置版本缺失，请联系管理员核查')
                merged = {
                    'name': row.connection_name,
                    'baseUrl': previous.base_url,
                    'adapterVersion': previous.adapter_version,
                    'config': previous.config,
                    **payload.model_dump(by_alias=True, exclude_unset=True, exclude={'revision'}),
                }
            else:
                merged = payload.model_dump(by_alias=True, exclude={'environment'})
            try:
                fields = ConnectionFields.model_validate(merged)
            except ValidationError:
                cls.fail('CONNECTION_CONFIG_INVALID', '连接字段、允许域名或超时配置不合法')
            environment = row.environment if row else payload.environment
            if await ProviderDao.unique_name(db, environment, fields.name, connection_id):
                cls.fail('CONNECTION_NAME_EXISTS', '该环境下连接名称已存在')
            audit = WriteService.audit(user)
            if row is None:
                row = await ProviderDao.add(
                    db,
                    HfProviderConnection,
                    connection_name=fields.name,
                    environment=environment,
                    status='0',
                    revision=1,
                    **audit,
                )
            else:
                row.connection_name = fields.name
                row.revision += 1
                row.update_by, row.update_time = audit['update_by'], audit['update_time']
            version_data = {
                'baseUrl': fields.base_url,
                'adapterVersion': fields.adapter_version,
                'config': fields.config.model_dump(by_alias=True),
            }
            digest = WriteService.digest(version_data)
            if previous is None or previous.config_hash != digest:
                version = await ProviderDao.add(
                    db,
                    HfProviderConnectionVersion,
                    connection_id=row.connection_id,
                    version_no=previous.version_no + 1 if previous else 1,
                    base_url=fields.base_url,
                    adapter_version=fields.adapter_version,
                    config=version_data['config'],
                    config_hash=digest,
                    **audit,
                )
                row.current_version_id = version.connection_version_id
                # 新配置没有测试/传输证据，不能沿用旧版本的启用结论。
                row.status = '0'
            await db.flush()
            return await WriteService.finish(
                db,
                user,
                path,
                key,
                data,
                await cls.result(db, row),
                'provider_connection',
                row.connection_id,
                method,
                api_prefix='/api/admin/v1',
            )
        except Exception:
            await db.rollback()
            raise
