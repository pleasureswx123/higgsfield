from sqlalchemy import func, select

from module_higgsfield.entity.do.asset_do import (
    HfUploadSession,
    HfUploadPart,
    HfUploadBinding,
    HfStoredFile,
    HfAsset,
    HfAssetVersion,
    HfFolderEntry,
)
from module_higgsfield.entity.do.project_do import HfAssetSpace
from module_higgsfield.entity.do.folder_do import HfFolder, HfRecycleEntry
from module_higgsfield.entity.do.favorite_do import HfFavorite
from module_higgsfield.entity.do.audit_do import HfAuditLog
from sqlalchemy import cast, String
from module_higgsfield.entity.vo.asset_formats import DOCUMENT_MIME_TYPES


class AssetDao:
    """上传与素材数据库操作；文件IO不在DAO执行。"""

    @staticmethod
    async def is_uploaded_version(db, version_id):
        return bool(await db.scalar(select(HfUploadBinding.binding_id).where(
            HfUploadBinding.asset_version_id == version_id
        ).limit(1)))

    @staticmethod
    async def asset_entry(db, asset_id):
        return await db.scalar(
            select(HfFolderEntry).where(HfFolderEntry.asset_id == asset_id).execution_options(populate_existing=True)
        )

    @staticmethod
    async def recycle(db, asset_id):
        return await db.scalar(
            select(HfRecycleEntry)
            .where(
                HfRecycleEntry.target_kind == 'asset',
                HfRecycleEntry.target_id == asset_id,
                HfRecycleEntry.state == 'active',
            )
            .with_for_update()
        )

    @staticmethod
    async def trash(db, project_id, owner_id, page_num, page_size):
        query = (
            select(HfRecycleEntry, HfAsset)
            .join(HfAsset, HfAsset.asset_id == HfRecycleEntry.target_id)
            .where(
                HfRecycleEntry.project_id == project_id,
                HfRecycleEntry.target_kind == 'asset',
                HfRecycleEntry.state == 'active',
                HfAsset.del_flag == '2',
            )
        )
        if owner_id is not None:
            query = query.where(HfAsset.create_user_id == owner_id)
        total = await db.scalar(select(func.count()).select_from(query.subquery()))
        rows = (
            await db.execute(
                query.order_by(HfRecycleEntry.deleted_time.desc(), HfRecycleEntry.recycle_id.desc())
                .offset((page_num - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return rows, total

    @staticmethod
    async def library(db, space_id, query, user_id=None):
        conditions = [HfAsset.space_id == space_id, HfAsset.del_flag == '0', HfFolderEntry.space_id == space_id]
        if query.folder_id:
            folder_id = int(query.folder_id)
            if query.include_descendants:
                tree = (
                    select(HfFolder.folder_id)
                    .where(HfFolder.folder_id == folder_id, HfFolder.space_id == space_id, HfFolder.del_flag == '0')
                    .cte('visible_folders', recursive=True)
                )
                tree = tree.union_all(
                    select(HfFolder.folder_id)
                    .join(tree, HfFolder.parent_id == tree.c.folder_id)
                    .where(HfFolder.space_id == space_id, HfFolder.del_flag == '0')
                )
                conditions.append(HfFolderEntry.folder_id.in_(select(tree.c.folder_id)))
            else:
                conditions.append(HfFolderEntry.folder_id == folder_id)
        elif not query.include_descendants:
            conditions.append(HfFolderEntry.folder_id.is_(None))
        if query.q.strip():
            conditions.append(HfAsset.asset_name.icontains(query.q.strip(), autoescape=True))
        if query.from_time:
            conditions.append(HfAsset.create_time >= query.from_time)
        if query.to_time:
            conditions.append(HfAsset.create_time < query.to_time)
        if query.file_type:
            if query.file_type in DOCUMENT_MIME_TYPES:
                conditions.append(select(HfAssetVersion.version_id).join(HfStoredFile, HfStoredFile.file_id == HfAssetVersion.file_id).where(
                    HfAssetVersion.version_id == HfAsset.current_version_id,
                    HfStoredFile.mime_type == DOCUMENT_MIME_TYPES[query.file_type]).exists())
            else:
                conditions.append(HfAsset.media_type == query.file_type)
        if query.activity == 'downloaded':
            conditions.append(select(HfAuditLog.audit_id).where(
                HfAuditLog.actor_kind == 'user', HfAuditLog.actor_id == user_id,
                HfAuditLog.object_type == 'asset', HfAuditLog.object_id == cast(HfAsset.asset_id, String),
                HfAuditLog.action == 'download_authorized').exists())
        elif query.activity == 'liked':
            conditions.append(select(HfFavorite.favorite_id).where(
                HfFavorite.user_id == user_id, HfFavorite.asset_id == HfAsset.asset_id,
                HfFavorite.del_flag == '0').exists())
        elif query.activity in ('generated', 'uploaded'):
            # 沿当前不可变版本的复制来源追溯，用 UNION 去重终止意外循环。
            source = select(HfAssetVersion.version_id.label('root_id'), HfAssetVersion.version_id,
                HfAssetVersion.source_asset_version_id, HfAssetVersion.source_output_id).join(
                    HfAsset, HfAsset.current_version_id == HfAssetVersion.version_id
                ).where(HfAsset.space_id == space_id, HfAsset.del_flag == '0').cte('asset_origin', recursive=True)
            source = source.union(select(source.c.root_id, HfAssetVersion.version_id,
                HfAssetVersion.source_asset_version_id, HfAssetVersion.source_output_id).join(
                    source, HfAssetVersion.version_id == source.c.source_asset_version_id))
            origin = select(source.c.version_id).where(source.c.root_id == HfAsset.current_version_id)
            if query.activity == 'generated':
                origin = origin.where(source.c.source_output_id.is_not(None))
            else:
                origin = origin.where(select(HfUploadBinding.binding_id).where(
                    HfUploadBinding.asset_version_id == source.c.version_id).exists())
            conditions.append(origin.exists())
        base = (
            select(HfAsset, HfFolderEntry)
            .join(HfFolderEntry, HfFolderEntry.asset_id == HfAsset.asset_id)
            .where(*conditions)
        )
        count = await db.scalar(select(func.count()).select_from(base.subquery()))
        rows = (
            await db.execute(
                base.order_by(HfAsset.create_time.desc(), HfAsset.asset_id.desc())
                .offset((query.page_num - 1) * query.page_size)
                .limit(query.page_size)
            )
        ).all()
        return rows, count

    @staticmethod
    async def entry(db, space_id, entry_id):
        return await db.scalar(
            select(HfFolderEntry)
            .where(HfFolderEntry.space_id == space_id, HfFolderEntry.entry_id == entry_id)
            .execution_options(populate_existing=True)
        )

    @staticmethod
    async def upload(db, upload_id, lock=False):
        statement = (
            select(HfUploadSession)
            .where(HfUploadSession.upload_id == upload_id)
            .execution_options(populate_existing=True)
        )
        return await db.scalar(statement.with_for_update() if lock else statement)

    @staticmethod
    async def parts(db, upload_id):
        return (
            await db.scalars(
                select(HfUploadPart).where(HfUploadPart.session_id == upload_id).order_by(HfUploadPart.part_no)
            )
        ).all()

    @staticmethod
    async def binding(db, upload_id):
        return await db.scalar(select(HfUploadBinding).where(HfUploadBinding.session_id == upload_id))

    @staticmethod
    async def file(db, file_id):
        return await db.get(HfStoredFile, file_id)

    @staticmethod
    async def asset(db, asset_id):
        return await db.scalar(
            select(HfAsset).where(HfAsset.asset_id == asset_id).execution_options(populate_existing=True)
        )

    @staticmethod
    async def project_id(db, asset_id):
        return await db.scalar(
            select(HfAssetSpace.project_id)
            .join(HfAsset, HfAsset.space_id == HfAssetSpace.space_id)
            .where(HfAsset.asset_id == asset_id, HfAssetSpace.kind == 'project')
        )

    @staticmethod
    async def version(db, version_id):
        return await db.get(HfAssetVersion, version_id)

    @staticmethod
    async def entries(db, space_id, folder_id):
        return (
            await db.scalars(
                select(HfFolderEntry).where(HfFolderEntry.space_id == space_id, HfFolderEntry.folder_id == folder_id)
            )
        ).all()

    @staticmethod
    async def add(db, model, **values):
        entity = model(**values)
        db.add(entity)
        await db.flush()
        return entity

    @staticmethod
    async def flush(db):
        await db.flush()
