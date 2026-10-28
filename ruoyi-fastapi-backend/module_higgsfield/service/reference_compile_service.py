"""固定引用授权与归一化编译；不提交供应商，不生成外部媒体地址。"""

from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.dao.element_dao import ElementDao
from module_higgsfield.dao.folder_dao import FolderDao
from module_higgsfield.entity.vo.reference_vo import MentionNode
from module_higgsfield.service.project_workspace_service import WorkspaceService


class ReferenceCompileService:
    fail = staticmethod(WorkspaceService.conflict)

    @staticmethod
    def compile(payload, snapshots):
        """同一版本/角色只占一个位置，保留每个引用键及固定来源映射。"""
        positions, media, mapping, sources = {}, [], {}, []
        for item in sorted(payload.references, key=lambda value: value.ordinal):
            identity = (item.asset_version_id, item.media_role)
            if identity not in positions:
                positions[identity] = len(media)
                media.append(
                    {
                        'ordinal': len(media),
                        'assetVersionId': item.asset_version_id,
                        'mediaRole': item.media_role,
                        **snapshots[item.asset_version_id],
                    }
                )
            ordinal = positions[identity]
            values = mapping.setdefault(item.reference_key, [])
            if ordinal not in values:
                values.append(ordinal)
            sources.append({**item.model_dump(by_alias=True), 'compiledOrdinal': ordinal})
        paragraphs = []
        for paragraph in payload.prompt.content:
            segments = []
            for node in paragraph.content:
                if isinstance(node, MentionNode):
                    segments.append(
                        {
                            'type': 'reference',
                            'referenceKey': node.reference_key,
                            'ordinals': list(mapping[node.reference_key]),
                        }
                    )
                else:
                    segments.append({'type': 'text', 'text': node.text})
            paragraphs.append(segments)
        return {
            'compilerVersion': 1,
            'media': media,
            'referenceOrdinals': mapping,
            'sources': sources,
            'promptParagraphs': paragraphs,
        }

    @classmethod
    async def resolve(cls, db, user, project_id, payload, role_media_types):
        """调用方传入已发布模型角色/媒体类型表，并在同一短事务保存快照；本方法不提交事务。"""
        await WorkspaceService.authorize(db, user, project_id, 'generation:create', write=True)
        space = await FolderDao.space(db, project_id)
        snapshots, revisions = {}, {}
        for item in payload.references:
            if item.asset_version_id not in snapshots:
                version = await AssetDao.version(db, int(item.asset_version_id))
                if version is None:
                    cls.fail('REFERENCE_UNAVAILABLE', '引用素材版本不存在')
                asset = await AssetDao.asset(db, version.asset_id)
                file = await AssetDao.file(db, version.file_id)
                if (
                    asset is None
                    or asset.space_id != space.space_id
                    or asset.del_flag != '0'
                    or file is None
                    or file.state != '1'
                ):
                    cls.fail('REFERENCE_UNAVAILABLE', '引用媒体不属于当前项目或已不可用')
                for permission in ('asset:read', 'asset:reference'):
                    await WorkspaceService.authorize(db, user, project_id, permission, owner_id=asset.create_user_id)
                snapshots[item.asset_version_id] = {
                    'assetId': str(asset.asset_id),
                    'fileId': str(file.file_id),
                    'mediaType': asset.media_type,
                    'mimeType': file.mime_type,
                    'byteSize': str(file.byte_size),
                    'sha256': file.sha256,
                    'width': file.width,
                    'height': file.height,
                    'seconds': str(file.seconds) if file.seconds is not None else None,
                }
            if snapshots[item.asset_version_id]['mediaType'] not in role_media_types.get(item.media_role, ()):
                cls.fail('REFERENCE_ROLE_UNSUPPORTED', '模型能力未开放此媒体角色或媒体类型不匹配')
            if item.element_revision_id:
                if item.element_revision_id not in revisions:
                    revision = await ElementDao.revision(db, int(item.element_revision_id))
                    if revision is None:
                        cls.fail('REFERENCE_UNAVAILABLE', '引用元素修订不存在')
                    element = await ElementDao.element(db, revision.element_id)
                    if element is None or element.space_id != space.space_id or element.del_flag != '0':
                        cls.fail('REFERENCE_UNAVAILABLE', '引用元素不属于当前项目或已删除')
                    await WorkspaceService.authorize(
                        db, user, project_id, 'element:read', owner_id=element.create_user_id
                    )
                    revisions[item.element_revision_id] = {
                        str(row.asset_version_id) for row in await ElementDao.revision_media(db, revision.revision_id)
                    }
                if item.asset_version_id not in revisions[item.element_revision_id]:
                    cls.fail('REFERENCE_REVISION_MISMATCH', '所选素材版本不属于指定元素修订')
        return cls.compile(payload, snapshots)
