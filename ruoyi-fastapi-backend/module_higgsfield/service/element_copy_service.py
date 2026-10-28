"""双向授权后整体复制固定修订；两项目按ID顺序加锁避免反向复制死锁。"""

from uuid import uuid4
from module_higgsfield.dao.element_dao import ElementDao
from module_higgsfield.dao.folder_dao import FolderDao
from module_higgsfield.dao.project_workspace_dao import WorkspaceDao
from module_higgsfield.entity.do.asset_do import HfAsset, HfAssetVersion, HfFolderEntry
from module_higgsfield.entity.do.copy_do import HfContentCopy
from module_higgsfield.entity.do.element_do import HfElement, HfPropertyDefinition
from module_higgsfield.entity.vo.element_vo import RevisionContent
from module_higgsfield.service.element_content_service import ElementContentService
from module_higgsfield.service.element_service import ElementService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService


class ElementCopyService:
    fail = staticmethod(WorkspaceService.conflict)

    @classmethod
    async def copy(cls, db, user, element_id, payload, key):
        path, data = f'/elements/{element_id}/copy', payload.model_dump(by_alias=True)
        try:
            await WriteService.lock(db, user, path, key)
            source_project = await ElementDao.project_id(db, element_id)
            target_project = int(payload.target_project_id)
            if source_project is None:
                cls.fail('RESOURCE_NOT_FOUND', '来源元素不存在或无权访问')
            for project_id in sorted({source_project, target_project}):
                await WorkspaceDao.lock_project(db, project_id)
            source, _, _ = await ElementService.authorized(db, user, element_id, 'element:read')
            await WorkspaceService.authorize(db, user, source_project, 'element:copy', owner_id=source.create_user_id)
            await WorkspaceService.authorize(
                db, user, target_project, 'element:create', write=True, owner_id=user.user.user_id
            )
            revision = await ElementDao.revision(db, int(payload.source_revision_id))
            if revision is None or revision.element_id != element_id:
                cls.fail('REFERENCE_UNAVAILABLE', '指定修订不属于来源元素')
            content_data = await ElementContentService.result(db, revision)
            content = RevisionContent(
                description=revision.description,
                propertyValues=content_data['propertyValues'],
                media=content_data['media'],
            )
            # 每次重放仍复核来源媒体使用权，不能借旧响应绕过撤权。
            await ElementContentService.validate(db, user, source_project, source.space_id, content)
            sources = await ElementDao.media_sources(db, [int(item.asset_version_id) for item in content.media])
            for _, asset, _ in sources:
                for permission in ('asset:read', 'asset:reference'):
                    await WorkspaceService.authorize(
                        db, user, source_project, permission, owner_id=asset.create_user_id
                    )
            if sources and target_project != source_project:
                await WorkspaceService.authorize(
                    db, user, target_project, 'asset:create', write=True, owner_id=user.user.user_id
                )
            replay = await WriteService.replay(db, user, path, key, data)
            if replay:
                await db.commit()
                return replay, True
            # 项目锁已按序持有，空间锁也按序取得。
            spaces = {}
            for project_id in sorted({source_project, target_project}):
                spaces[project_id] = await FolderDao.space(db, project_id, lock=True)
            target_space = spaces[target_project]
            if await ElementDao.alias_exists(db, target_space.space_id, payload.alias):
                cls.fail('ALIAS_CONFLICT', '目标项目已使用该别名')
            audit, version_map = WriteService.audit(user), {}
            if source_project != target_project:
                for version, asset, file in sources:
                    copied_asset = await ElementDao.add(
                        db,
                        HfAsset,
                        space_id=target_space.space_id,
                        asset_name=asset.asset_name,
                        media_type=asset.media_type,
                        create_user_id=user.user.user_id,
                        **audit,
                    )
                    copied_version = await ElementDao.add(
                        db,
                        HfAssetVersion,
                        asset_id=copied_asset.asset_id,
                        version_no=1,
                        file_id=file.file_id,
                        source_asset_version_id=version.version_id,
                        media_metadata=version.media_metadata,
                        create_user_id=user.user.user_id,
                        **audit,
                    )
                    copied_asset.current_version_id = copied_version.version_id
                    await ElementDao.add(
                        db, HfFolderEntry, space_id=target_space.space_id, asset_id=copied_asset.asset_id, **audit
                    )
                    version_map[str(version.version_id)] = str(copied_version.version_id)
                    await cls.evidence(
                        db, user, 'asset', source_project, version.version_id, target_project, copied_version.version_id
                    )
                values = []
                for snapshot in revision.property_snapshot:
                    definition = await cls.target_definition(db, user, target_space.space_id, source_project, snapshot)
                    values.append(
                        {
                            'definitionId': str(definition.property_id),
                            'definitionVersion': definition.version_no,
                            'value': snapshot['value'],
                        }
                    )
                content.property_values = RevisionContent(propertyValues=values).property_values
                for media in content.media:
                    media.asset_version_id = version_map[media.asset_version_id]
            # 新媒体均来自已授权的源版本；不额外要求目标下载或全项目读取权限。
            snapshots = revision.property_snapshot
            if source_project != target_project:
                snapshots = []
                for value in content.property_values:
                    definition = await ElementDao.definition(db, int(value.definition_id))
                    snapshots.append(
                        {
                            'definitionId': str(definition.property_id),
                            'definitionVersion': definition.version_no,
                            'propertyKey': definition.property_key,
                            'name': definition.property_name,
                            'valueType': definition.value_type,
                            'options': definition.options,
                            'value': value.value,
                        }
                    )
                snapshots.sort(key=lambda item: item['propertyKey'])
            copied = await ElementDao.add(
                db,
                HfElement,
                space_id=target_space.space_id,
                element_name=payload.name or source.element_name,
                alias=payload.alias,
                category=source.category,
                create_user_id=user.user.user_id,
                **audit,
            )
            copied_revision = await ElementContentService.append(
                db, user, copied, content, snapshots, content_data['label']
            )
            await cls.evidence(
                db, user, 'element', source_project, revision.revision_id, target_project, copied_revision.revision_id
            )
            return await WriteService.finish(
                db, user, path, key, data, ElementService.result(copied, target_project), 'element', copied.element_id
            )
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    async def evidence(db, user, kind, source_project, source_version, target_project, target_version):
        await ElementDao.add(
            db,
            HfContentCopy,
            target_kind=kind,
            source_project_id=source_project,
            source_version_id=source_version,
            target_project_id=target_project,
            target_version_id=target_version,
            actor_id=user.user.user_id,
            **WriteService.audit(user),
        )

    @classmethod
    async def target_definition(cls, db, user, space_id, source_project, snapshot):
        def matches(row):
            return (
                row.property_name == snapshot['name']
                and row.value_type == snapshot['valueType']
                and row.options == snapshot['options']
            )

        property_key = snapshot['propertyKey']
        existing = await ElementDao.latest_definition(db, space_id, property_key)
        if existing and matches(existing):
            return existing
        if existing:
            # 同名但不兼容时创建独立来源键，不发布或覆盖目标已有属性定义。
            property_key = f'copy_{source_project}_{snapshot["definitionId"]}'
            existing = await ElementDao.latest_definition(db, space_id, property_key)
            if existing and matches(existing):
                return existing
            if existing:
                property_key += '_' + uuid4().hex[:12]
        return await ElementDao.add(
            db,
            HfPropertyDefinition,
            space_id=space_id,
            property_key=property_key,
            version_no=1,
            property_name=snapshot['name'],
            value_type=snapshot['valueType'],
            options=snapshot['options'],
            **WriteService.audit(user),
        )
