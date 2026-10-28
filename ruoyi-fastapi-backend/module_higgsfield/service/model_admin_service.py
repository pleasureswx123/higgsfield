"""后台模型登记；所有新版本保持草稿，不暗示已完成联调或发布。"""

from common.vo import PageModel
from exceptions.exception import PermissionException
from module_higgsfield.dao.model_dao import ModelDao
from module_higgsfield.entity.do.model_do import HfModelProfile, HfModelProfileVersion, HfModelVariant
from module_higgsfield.entity.vo.model_capability_vo import ModelCapabilities
from module_higgsfield.service.model_capability_service import ModelCapabilityService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService
from module_higgsfield.entity.do.audit_do import HfAuditLog


class ModelAdminService:
    fail = staticmethod(WorkspaceService.conflict)

    @classmethod
    def validate_variants(cls, capabilities, variants, required=False):
        if required and not variants:
            cls.fail('MODEL_VARIANTS_REQUIRED', '验证或发布前必须登记至少一个完整规格')
        rules = capabilities.variant_dimensions
        for variant in variants:
            if set(variant.dimensions) != set(rules) or any(
                not rule.accepts(variant.dimensions[name]) for name, rule in rules.items()
            ):
                cls.fail('MODEL_VARIANT_INVALID', '已有规格与能力维度不兼容，请建立新能力版本')

    @classmethod
    async def mutate(cls, db, user, version_id, action, payload, key):
        cls.require(
            user,
            {'edit': 'model:write', 'verify': 'model:verify', 'publish': 'model:publish', 'disable': 'model:publish'}[
                action
            ],
        )
        path = f'/model-profile-versions/{version_id}' + ('' if action == 'edit' else f'/{action}')
        method, prefix = ('PATCH' if action == 'edit' else 'POST'), '/api/admin/v1'
        data = payload.model_dump(by_alias=True, exclude_unset=True)
        try:
            await WriteService.lock(db, user, path, key, api_prefix=prefix)
            row = await ModelDao.version(db, version_id, lock=True)
            if row is None:
                cls.fail('RESOURCE_NOT_FOUND', '模型能力版本不存在')
            replay = await WriteService.replay(db, user, path, key, data, method, api_prefix=prefix)
            if replay:
                await db.commit()
                return replay, True
            WorkspaceService.check_revision(row, payload.revision)
            before = {
                'status': row.status,
                'revision': str(row.revision),
                'configHash': WriteService.digest(
                    {
                        'alias': row.gateway_alias,
                        'underlying': row.underlying_model_id,
                        'capabilities': row.capabilities,
                    }
                ),
            }
            variants = await ModelDao.variants(db, version_id)
            if action == 'edit':
                if row.status != '0':
                    cls.fail('MODEL_VERSION_IMMUTABLE', '只有草稿能力版本可编辑')
                fields = payload.model_fields_set
                if 'capabilities' in fields:
                    ModelCapabilityService.validate_configuration(payload.capabilities)
                    cls.validate_variants(payload.capabilities, variants)
                    row.capabilities = payload.capabilities.model_dump(by_alias=True)
                if 'gateway_alias' in fields:
                    row.gateway_alias = payload.gateway_alias
                if 'underlying_model_id' in fields:
                    row.underlying_model_id = payload.underlying_model_id
            else:
                allowed = {'verify': {'0'}, 'publish': {'1'}, 'disable': {'0', '1', '2'}}[action]
                if row.status not in allowed:
                    cls.fail('MODEL_STATE_CONFLICT', '当前能力状态不允许该操作')
                if action in ('verify', 'publish'):
                    capabilities = ModelCapabilities.model_validate(row.capabilities)
                    ModelCapabilityService.validate_configuration(capabilities)
                    cls.validate_variants(capabilities, variants, required=True)
                if action == 'verify':
                    row.verification_ref, row.status = payload.verification_ref, '1'
                elif action == 'publish':
                    if not row.verification_ref:
                        cls.fail('MODEL_EVIDENCE_REQUIRED', '缺少已审阅的联调证据')
                    row.status = '2'
                else:
                    row.status = '3'
            audit = WriteService.audit(user)
            row.revision += 1
            row.update_by, row.update_time = audit['update_by'], audit['update_time']
            after = {
                'status': row.status,
                'revision': str(row.revision),
                'configHash': WriteService.digest(
                    {
                        'alias': row.gateway_alias,
                        'underlying': row.underlying_model_id,
                        'capabilities': row.capabilities,
                    }
                ),
                'verificationRef': row.verification_ref,
                'variantIds': [str(item.variant_id) for item in variants],
            }
            await ModelDao.add(
                db,
                HfAuditLog,
                actor_id=user.user.user_id,
                actor_kind='user',
                object_type='model_profile_version',
                object_id=str(version_id),
                action='model.' + action,
                request_id=WriteService.digest({'prefix': prefix, 'path': path, 'key': key}),
                before_after={'before': before, 'after': after},
                reason=getattr(payload, 'reason', None),
                **audit,
            )
            return await WriteService.finish(
                db, user, path, key, data, cls.result(row), 'model_version', version_id, method, api_prefix=prefix
            )
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    def require(user, permission):
        if '*:*:*' not in user.permissions and permission not in user.permissions:
            raise PermissionException(message='没有执行模型管理操作的权限')

    @staticmethod
    def result(row):
        if isinstance(row, HfModelProfile):
            return {
                'id': str(row.model_id),
                'connectionId': str(row.connection_id),
                'code': row.code,
                'displayName': row.display_name,
                'kind': row.kind,
            }
        if isinstance(row, HfModelVariant):
            return {
                'id': str(row.variant_id),
                'modelVersionId': str(row.model_version_id),
                'variantKey': row.variant_key,
                'dimensions': row.dimensions,
            }
        return {
            'id': str(row.model_version_id),
            'modelId': str(row.model_id),
            'versionNo': row.version_no,
            'gatewayAlias': row.gateway_alias,
            'underlyingModelId': row.underlying_model_id,
            'region': row.region,
            'capabilities': row.capabilities,
            'schemaVersion': row.schema_version,
            'status': {'0': 'draft', '1': 'verified', '2': 'published', '3': 'disabled'}[row.status],
            'revision': str(row.revision),
            'verificationRef': row.verification_ref,
        }

    @classmethod
    async def get(cls, db, user, version_id):
        cls.require(user, 'model:read')
        row = await ModelDao.version(db, version_id)
        if row is None:
            cls.fail('RESOURCE_NOT_FOUND', '模型能力版本不存在')
        return cls.result(row)

    @classmethod
    async def listing(cls, db, user, kind, parent_id=None, page_num=1, page_size=30, query=None):
        cls.require(user, 'model:read')
        rows, total = await ModelDao.page(db, kind, parent_id, page_num, page_size, query)
        return PageModel(
            rows=[cls.result(row) for row in rows],
            total=total,
            pageNum=page_num,
            pageSize=page_size,
            hasNext=page_num * page_size < total,
        )

    @classmethod
    async def create(cls, db, user, kind, payload, key, parent_id=None):
        cls.require(user, 'model:write')
        path = (
            '/model-profiles'
            if kind == 'model'
            else (
                f'/model-profiles/{parent_id}/versions'
                if kind == 'version'
                else f'/model-profile-versions/{parent_id}/variants'
            )
        )
        data = payload.model_dump(by_alias=True)
        try:
            await WriteService.lock(db, user, path, key, api_prefix='/api/admin/v1')
            if kind == 'model':
                parent = await ModelDao.connection(db, int(payload.connection_id))
            elif kind == 'version':
                parent = await ModelDao.model(db, parent_id, lock=True)
            else:
                parent = await ModelDao.version(db, parent_id, lock=True)
            if parent is None:
                cls.fail('RESOURCE_NOT_FOUND', '供应商连接或模型归属不存在')
            replay = await WriteService.replay(db, user, path, key, data, api_prefix='/api/admin/v1')
            if replay:
                await db.commit()
                return replay, True
            audit = WriteService.audit(user)
            if kind == 'model':
                if await ModelDao.code_exists(db, int(payload.connection_id), payload.code):
                    cls.fail('MODEL_CODE_EXISTS', '连接下模型稳定码已存在')
                row = await ModelDao.add(
                    db,
                    HfModelProfile,
                    **payload.model_dump(exclude={'connection_id'}),
                    connection_id=int(payload.connection_id),
                    **audit,
                )
            elif kind == 'version':
                ModelCapabilityService.validate_configuration(payload.capabilities)
                row = await ModelDao.add(
                    db,
                    HfModelProfileVersion,
                    model_id=parent_id,
                    version_no=await ModelDao.next_version(db, parent_id),
                    gateway_alias=payload.gateway_alias,
                    underlying_model_id=payload.underlying_model_id,
                    region=payload.region,
                    capabilities=payload.capabilities.model_dump(by_alias=True),
                    schema_version=1,
                    status='0',
                    revision=1,
                    **audit,
                )
            else:
                if parent.status != '0':
                    cls.fail('MODEL_VERSION_IMMUTABLE', '只有草稿能力版本可增加计价规格')
                capabilities = ModelCapabilities.model_validate(parent.capabilities)
                rules = capabilities.variant_dimensions
                if set(payload.dimensions) != set(rules):
                    cls.fail('MODEL_VARIANT_INCOMPLETE', '规格必须恰好提供全部已声明计价维度')
                for name, rule in rules.items():
                    if not rule.accepts(payload.dimensions[name]):
                        cls.fail('MODEL_VARIANT_INVALID', f'计价维度不符合能力定义：{name}')
                dimensions = {
                    name: int(value) if isinstance(value, float) and value.is_integer() else value
                    for name, value in payload.dimensions.items()
                }
                variant_key = 'v1:' + WriteService.digest(dimensions)
                if await ModelDao.variant_exists(db, parent_id, variant_key):
                    cls.fail('MODEL_VARIANT_EXISTS', '相同精确规格已存在')
                row = await ModelDao.add(
                    db,
                    HfModelVariant,
                    model_version_id=parent_id,
                    variant_key=variant_key,
                    dimensions=dimensions,
                    **audit,
                )
                parent.revision += 1
                parent.update_by, parent.update_time = audit['update_by'], audit['update_time']
            return await WriteService.finish(
                db,
                user,
                path,
                key,
                data,
                cls.result(row),
                'model_' + kind,
                row.model_id if kind == 'model' else row.model_version_id if kind == 'version' else row.variant_id,
                api_prefix='/api/admin/v1',
            )
        except Exception:
            await db.rollback()
            raise
