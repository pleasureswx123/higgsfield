"""先在 SQL 中过滤授权候选，再统计和分页。"""

from sqlalchemy import select, literal, func, or_, and_, false, union_all
from module_higgsfield.entity.do.asset_do import HfAsset, HfAssetVersion, HfStoredFile
from module_higgsfield.entity.do.element_do import HfElement, HfElementRevisionMedia


class ReferenceDao:
    @staticmethod
    def owner_condition(scopes, permission, owner_column, user_id):
        scope = scopes.get(permission)
        if scope == 'project':
            return literal(True)
        if scope == 'own':
            return owner_column == user_id
        return false()

    @classmethod
    async def search(cls, db, space_id, user_id, scopes, query):
        media = (
            select(HfAssetVersion.version_id)
            .join(HfAsset, HfAsset.asset_id == HfAssetVersion.asset_id)
            .join(HfStoredFile, HfStoredFile.file_id == HfAssetVersion.file_id)
            .where(
                HfAsset.space_id == space_id,
                HfAsset.del_flag == '0',
                HfStoredFile.state == '1',
                or_(
                    and_(HfAsset.media_type == 'image', HfStoredFile.mime_type.startswith('image/')),
                    and_(HfAsset.media_type == 'video', HfStoredFile.mime_type.startswith('video/')),
                ),
                cls.owner_condition(scopes, 'asset:read', HfAsset.create_user_id, user_id),
                cls.owner_condition(scopes, 'asset:reference', HfAsset.create_user_id, user_id),
            )
        )
        assets = select(
            literal('asset').label('kind'),
            HfAsset.asset_id.label('id'),
            HfAsset.asset_name.label('name'),
            HfAsset.current_version_id.label('version_id'),
            HfAsset.media_type.label('media_type'),
            HfAsset.create_time.label('created'),
        ).where(HfAsset.space_id == space_id, HfAsset.current_version_id.in_(media))
        linked = select(HfElementRevisionMedia.media_id).where(
            HfElementRevisionMedia.element_revision_id == HfElement.current_revision_id
        )
        # 元素参考图必须为图片，不能将视频或文档按图片角色输出。
        image_media = media.where(HfAsset.media_type == 'image')
        invalid = linked.where(HfElementRevisionMedia.asset_version_id.not_in(image_media))
        elements = select(
            literal('element').label('kind'),
            HfElement.element_id.label('id'),
            HfElement.element_name.label('name'),
            HfElement.current_revision_id.label('version_id'),
            literal('image').label('media_type'),
            HfElement.create_time.label('created'),
        ).where(
            HfElement.space_id == space_id,
            HfElement.del_flag == '0',
            linked.exists(),
            ~invalid.exists(),
            cls.owner_condition(scopes, 'element:read', HfElement.create_user_id, user_id),
        )
        if query.element_id is not None:
            elements = elements.where(HfElement.element_id == int(query.element_id))
        if query.q.strip():
            assets = assets.where(HfAsset.asset_name.icontains(query.q.strip(), autoescape=True))
            elements = elements.where(
                or_(
                    HfElement.element_name.icontains(query.q.strip(), autoescape=True),
                    HfElement.alias.icontains(query.q.strip(), autoescape=True),
                )
            )
        combined = (
            assets if query.kind == 'asset' else elements if query.kind == 'element' else union_all(assets, elements)
        ).subquery()
        total = await db.scalar(select(func.count()).select_from(combined))
        rows = (
            (
                await db.execute(
                    select(combined)
                    .order_by(combined.c.created.desc(), combined.c.kind, combined.c.id.desc())
                    .offset((query.page_num - 1) * query.page_size)
                    .limit(query.page_size)
                )
            )
            .mappings()
            .all()
        )
        return rows, total

    @staticmethod
    async def revision_media(db, revision_ids):
        if not revision_ids:
            return []
        return (
            await db.scalars(
                select(HfElementRevisionMedia)
                .where(HfElementRevisionMedia.element_revision_id.in_(revision_ids))
                .order_by(HfElementRevisionMedia.element_revision_id, HfElementRevisionMedia.ordinal)
            )
        ).all()
