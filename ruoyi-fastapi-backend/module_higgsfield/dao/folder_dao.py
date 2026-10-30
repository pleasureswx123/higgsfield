from sqlalchemy import exists, func, select
from sqlalchemy.orm import aliased

from module_higgsfield.entity.do.folder_do import HfFolder, HfRecycleEntry
from module_higgsfield.entity.do.project_do import HfAssetSpace


class FolderDao:
    """目录数据库操作，空间锁覆盖整次层级变更。"""

    @staticmethod
    async def asset_counts(db, space_id):
        from module_higgsfield.entity.do.asset_do import HfAsset, HfFolderEntry
        rows = (await db.execute(
            select(HfFolderEntry.folder_id, func.count(HfAsset.asset_id))
            .join(HfAsset, HfAsset.asset_id == HfFolderEntry.asset_id)
            .where(HfFolderEntry.space_id == space_id, HfAsset.space_id == space_id, HfAsset.del_flag == '0')
            .group_by(HfFolderEntry.folder_id)
        )).all()
        return {'total': sum(count for _, count in rows),
                'folders': {str(folder_id): count for folder_id, count in rows if folder_id is not None}}

    @staticmethod
    async def space(db, project_id, lock=False):
        query = select(HfAssetSpace).where(HfAssetSpace.project_id == project_id, HfAssetSpace.kind == 'project')
        return await db.scalar(query.with_for_update() if lock else query)

    @staticmethod
    async def project_id(db, folder_id):
        return await db.scalar(
            select(HfAssetSpace.project_id)
            .join(HfFolder, HfFolder.space_id == HfAssetSpace.space_id)
            .where(HfFolder.folder_id == folder_id, HfAssetSpace.kind == 'project')
        )

    @staticmethod
    async def get(db, folder_id):
        return await db.get(HfFolder, folder_id, populate_existing=True)

    @staticmethod
    async def siblings(db, space_id, parent_id):
        return (
            await db.scalars(
                select(HfFolder)
                .where(HfFolder.space_id == space_id, HfFolder.parent_id == parent_id, HfFolder.del_flag == '0')
                .order_by(HfFolder.folder_id)
            )
        ).all()

    @staticmethod
    async def list(db, space_id, query):
        conditions = [
            HfFolder.space_id == space_id,
            HfFolder.del_flag == '0',
            HfFolder.folder_kind == query.folder_kind,
        ]
        if query.q.strip():
            conditions.append(HfFolder.folder_name.icontains(query.q.strip(), autoescape=True))
        else:
            conditions.append(HfFolder.parent_id == (int(query.parent_id) if query.parent_id else None))
        total = await db.scalar(select(func.count()).select_from(HfFolder).where(*conditions))
        order = {
            'createdAsc': HfFolder.create_time.asc(),
            'createdDesc': HfFolder.create_time.desc(),
            'updatedDesc': HfFolder.update_time.desc(),
            'nameAsc': HfFolder.normalized_name.asc(),
            'nameDesc': HfFolder.normalized_name.desc(),
        }[query.sort]
        child = aliased(HfFolder)
        has_children = exists(
            select(child.folder_id).where(
                child.parent_id == HfFolder.folder_id, child.del_flag == '0', child.space_id == space_id
            )
        )
        rows = (
            await db.execute(
                select(HfFolder, has_children)
                .where(*conditions)
                .order_by(order, HfFolder.folder_id)
                .offset((query.page_num - 1) * query.page_size)
                .limit(query.page_size)
            )
        ).all()
        return rows, total

    @staticmethod
    async def recycle(db, folder_id):
        return await db.scalar(
            select(HfRecycleEntry)
            .where(
                HfRecycleEntry.target_id == folder_id,
                HfRecycleEntry.target_kind == 'folder',
                HfRecycleEntry.state == 'active',
            )
            .with_for_update()
        )

    @staticmethod
    async def trash(db, project_id, page_num, page_size):
        conditions = [
            HfRecycleEntry.project_id == project_id,
            HfRecycleEntry.state == 'active',
            HfRecycleEntry.target_kind == 'folder',
        ]
        total = await db.scalar(select(func.count()).select_from(HfRecycleEntry).where(*conditions))
        rows = (
            await db.scalars(
                select(HfRecycleEntry)
                .where(*conditions)
                .order_by(HfRecycleEntry.deleted_time.desc(), HfRecycleEntry.recycle_id.desc())
                .offset((page_num - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return rows, total

    @staticmethod
    async def add(db, model, **values):
        entity = model(**values)
        db.add(entity)
        await db.flush()
        return entity

    @staticmethod
    async def flush(db):
        await db.flush()
