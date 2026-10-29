"""固定元素生成资料；调用方在授权且持有项目写锁的事务内使用。"""

from module_higgsfield.dao.element_dao import ElementDao
from module_higgsfield.entity.do.element_do import HfElementRevision, HfElementRevisionLabel, HfElementRevisionMedia
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService


class ElementContentService:
    fail = staticmethod(WorkspaceService.conflict)

    @classmethod
    async def validate(cls, db, user, project_id, space_id, content):
        snapshots, keys = [], set()
        for item in content.property_values:
            definition = await ElementDao.definition(db, int(item.definition_id))
            if (
                definition is None
                or definition.space_id != space_id
                or definition.version_no != item.definition_version
            ):
                cls.fail('PROPERTY_DEFINITION_INVALID', '属性定义版本不存在或不属于当前项目')
            if definition.property_key in keys:
                cls.fail('PROPERTY_DUPLICATE', '同一属性不能同时填写多个定义版本')
            keys.add(definition.property_key)
            value = item.value
            if value is not None:
                if definition.value_type == 'text' and not isinstance(value, str):
                    cls.fail('PROPERTY_VALUE_INVALID', '文本属性必须填写字符串')
                if definition.value_type == 'single_select' and (
                    not isinstance(value, str) or value not in definition.options
                ):
                    cls.fail('PROPERTY_VALUE_INVALID', '单选属性必须选择定义中的选项')
                if definition.value_type == 'multi_select' and (
                    not isinstance(value, list) or any(option not in definition.options for option in value)
                ):
                    cls.fail('PROPERTY_VALUE_INVALID', '多选属性必须使用定义中的合法选项数组')
            snapshots.append(
                {
                    'definitionId': str(definition.property_id),
                    'definitionVersion': definition.version_no,
                    'propertyKey': definition.property_key,
                    'name': definition.property_name,
                    'valueType': definition.value_type,
                    'options': list(definition.options),
                    'value': value,
                }
            )
        versions = [int(item.asset_version_id) for item in content.media]
        sources = await ElementDao.media_sources(db, versions)
        if len(sources) != len(versions):
            cls.fail('REFERENCE_UNAVAILABLE', '所选素材版本不存在或不可用')
        for version, asset, file in sources:
            await WorkspaceService.authorize(db, user, project_id, 'asset:read', owner_id=asset.create_user_id)
            if asset.space_id != space_id or asset.del_flag != '0':
                cls.fail('REFERENCE_UNAVAILABLE', '素材必须来自当前项目的可用素材')
            if (asset.media_type not in ('image', 'video') or file.state != '1'
                    or not file.mime_type.startswith(asset.media_type + '/')):
                cls.fail('REFERENCE_MEDIA_INVALID', '元素素材必须是归档就绪的图片或视频版本')
        return sorted(snapshots, key=lambda item: item['propertyKey'])

    @staticmethod
    async def append(db, user, element, content, snapshots, label=''):
        previous = await ElementDao.revision(db, element.current_revision_id) if element.current_revision_id else None
        audit = WriteService.audit(user)
        revision = await ElementDao.add(
            db,
            HfElementRevision,
            element_id=element.element_id,
            revision_no=previous.revision_no + 1 if previous else 1,
            description=content.description,
            property_snapshot=snapshots,
            create_user_id=user.user.user_id,
            **audit,
        )
        await ElementDao.add(
            db,
            HfElementRevisionLabel,
            element_revision_id=revision.revision_id,
            label=label,
            revision=1,
            update_user_id=user.user.user_id,
            **audit,
        )
        for item in content.media:
            await ElementDao.add(
                db,
                HfElementRevisionMedia,
                element_revision_id=revision.revision_id,
                asset_version_id=int(item.asset_version_id),
                ordinal=item.ordinal,
                is_primary='Y' if item.is_primary else 'N',
                **audit,
            )
        element.current_revision_id = revision.revision_id
        await db.flush()
        return revision

    @staticmethod
    async def result(db, revision):
        label = await ElementDao.label(db, revision.revision_id)
        media = await ElementDao.revision_media(db, revision.revision_id)
        return {
            'id': str(revision.revision_id),
            'elementId': str(revision.element_id),
            'revisionNo': revision.revision_no,
            'description': revision.description,
            'propertyValues': [
                {key: item[key] for key in ('definitionId', 'definitionVersion', 'value')}
                for item in revision.property_snapshot
            ],
            'propertySnapshot': revision.property_snapshot,
            'media': [
                {
                    'assetVersionId': str(item.asset_version_id),
                    'ordinal': item.ordinal,
                    'isPrimary': item.is_primary == 'Y',
                }
                for item in media
            ],
            'label': label.label if label else '',
            'labelRevision': str(label.revision) if label else None,
        }
