from sqlalchemy import func, select, or_
from module_higgsfield.dao.project_dao import ProjectDao
from module_higgsfield.entity.do.folder_do import HfRecycleEntry
from module_higgsfield.entity.do.favorite_do import HfFavorite

from module_higgsfield.entity.do.asset_do import HfAsset, HfAssetVersion, HfStoredFile
from module_higgsfield.entity.do.element_do import (
    HfElement,
    HfElementRevision,
    HfElementRevisionLabel,
    HfElementRevisionMedia,
    HfPropertyDefinition,
)
from module_higgsfield.entity.do.project_do import HfAssetSpace, HfProject, HfProjectMember, HfProjectRolePermission


class ElementDao:
    @staticmethod
    async def recycle(db, element_id):
        return await db.scalar(
            select(HfRecycleEntry)
            .where(
                HfRecycleEntry.target_kind == 'element',
                HfRecycleEntry.target_id == element_id,
                HfRecycleEntry.state == 'active',
            )
            .with_for_update()
        )

    @staticmethod
    async def trash(db, project_id, owner_id, page_num, page_size):
        statement = (
            select(HfRecycleEntry, HfElement)
            .join(HfElement, HfElement.element_id == HfRecycleEntry.target_id)
            .where(
                HfRecycleEntry.project_id == project_id,
                HfRecycleEntry.target_kind == 'element',
                HfRecycleEntry.state == 'active',
                HfElement.del_flag == '2',
            )
        )
        if owner_id is not None:
            statement = statement.where(HfElement.create_user_id == owner_id)
        total = await db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = (
            await db.execute(
                statement.order_by(HfRecycleEntry.deleted_time.desc(), HfRecycleEntry.recycle_id.desc())
                .offset((page_num - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return rows, total

    @staticmethod
    async def in_folder(db, space_id, folder_id):
        return (
            await db.scalars(
                select(HfElement).where(
                    HfElement.space_id == space_id, HfElement.folder_id == folder_id, HfElement.del_flag == '0'
                )
            )
        ).all()

    @staticmethod
    async def list_elements(db, user_id, query, status_code):
        visible = ProjectDao.visible_query(user_id).with_only_columns(HfProjectMember.project_id).subquery()
        statement = (
            select(HfElement, HfAssetSpace.project_id, HfProject.project_name,
                   HfElementRevision.description, HfElementRevisionLabel.label, HfElementRevision.revision_no)
            .join(HfAssetSpace, HfElement.space_id == HfAssetSpace.space_id)
            .join(HfProject, HfProject.project_id == HfAssetSpace.project_id)
            .join(HfElementRevision, HfElementRevision.revision_id == HfElement.current_revision_id)
            .outerjoin(HfElementRevisionLabel, HfElementRevisionLabel.element_revision_id == HfElementRevision.revision_id)
            .join(HfProjectMember, HfProjectMember.project_id == HfAssetSpace.project_id)
            .join(HfProjectRolePermission, HfProjectRolePermission.role_id == HfProjectMember.role_id)
            .where(
                HfElement.del_flag == '0',
                HfAssetSpace.kind == 'project',
                HfAssetSpace.project_id.in_(select(visible.c.project_id)),
                HfProjectMember.user_id == user_id,
                HfProjectMember.status == '0',
                HfProjectRolePermission.permission_code == 'element:read',
                or_(HfProjectRolePermission.data_scope == 'project', HfElement.create_user_id == user_id),
            )
        )
        if query.project_id:
            statement = statement.where(HfAssetSpace.project_id == int(query.project_id))
        if query.scope == 'mine':
            favorite = select(HfFavorite.favorite_id).where(
                HfFavorite.user_id == user_id,
                HfFavorite.element_id == HfElement.element_id,
                HfFavorite.del_flag == '0',
            ).exists()
            # 个人来源筛选在分页与计数前执行，不改变上方项目/对象读取授权。
            if query.mine_filter == 'created':
                statement = statement.where(HfElement.create_user_id == user_id)
            elif query.mine_filter == 'favorites':
                statement = statement.where(favorite)
            else:
                statement = statement.where(or_(HfElement.create_user_id == user_id, favorite))
        if query.folder_id:
            statement = statement.where(HfElement.folder_id == int(query.folder_id))
        if query.q.strip():
            statement = statement.where(
                or_(
                    HfElement.element_name.icontains(query.q.strip(), autoescape=True),
                    HfElement.alias.icontains(query.q.strip(), autoescape=True),
                )
            )
        if query.category:
            statement = statement.where(HfElement.category == query.category)
        if query.work_status:
            statement = statement.where(HfElement.work_status == status_code[query.work_status])
        if query.status_group:
            statement = statement.where(
                HfElement.work_status.in_(['3'] if query.status_group == 'active' else ['0', '1', '2'])
            )
        total = await db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = (
            await db.execute(
                statement.order_by(HfElement.create_time.desc(), HfElement.element_id.desc())
                .offset((query.page_num - 1) * query.page_size)
                .limit(query.page_size)
            )
        ).all()
        return rows, total

    @staticmethod
    async def space_project(db, space_id):
        return await db.scalar(
            select(HfAssetSpace.project_id).where(HfAssetSpace.space_id == space_id, HfAssetSpace.kind == 'project')
        )

    @staticmethod
    async def definitions(db, space_id, page_num, page_size):
        latest = (
            select(HfPropertyDefinition.property_key, func.max(HfPropertyDefinition.version_no).label('version'))
            .where(HfPropertyDefinition.space_id == space_id)
            .group_by(HfPropertyDefinition.property_key)
            .subquery()
        )
        statement = (
            select(HfPropertyDefinition)
            .join(
                latest,
                (HfPropertyDefinition.property_key == latest.c.property_key)
                & (HfPropertyDefinition.version_no == latest.c.version),
            )
            .where(HfPropertyDefinition.space_id == space_id)
        )
        total = await db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = (
            await db.scalars(
                statement.order_by(HfPropertyDefinition.property_key)
                .offset((page_num - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return rows, total

    @staticmethod
    async def element(db, element_id):
        return await db.scalar(
            select(HfElement).where(HfElement.element_id == element_id).execution_options(populate_existing=True)
        )

    @staticmethod
    async def project_id(db, element_id):
        return await db.scalar(
            select(HfAssetSpace.project_id)
            .join(HfElement, HfElement.space_id == HfAssetSpace.space_id)
            .where(HfElement.element_id == element_id, HfAssetSpace.kind == 'project')
        )

    @staticmethod
    async def alias_exists(db, space_id, alias, excluding=None):
        query = select(HfElement.element_id).where(HfElement.space_id == space_id, HfElement.alias == alias)
        if excluding is not None:
            query = query.where(HfElement.element_id != excluding)
        return await db.scalar(query)

    @staticmethod
    async def revision(db, revision_id):
        return await db.get(HfElementRevision, revision_id)

    @staticmethod
    async def revision_media(db, revision_id):
        return (
            await db.scalars(
                select(HfElementRevisionMedia)
                .where(HfElementRevisionMedia.element_revision_id == revision_id)
                .order_by(HfElementRevisionMedia.ordinal)
            )
        ).all()

    @staticmethod
    async def label(db, revision_id):
        return await db.scalar(
            select(HfElementRevisionLabel).where(HfElementRevisionLabel.element_revision_id == revision_id)
        )

    @staticmethod
    async def definition(db, definition_id):
        return await db.get(HfPropertyDefinition, definition_id)

    @staticmethod
    async def latest_definition(db, space_id, key):
        return await db.scalar(
            select(HfPropertyDefinition)
            .where(HfPropertyDefinition.space_id == space_id, HfPropertyDefinition.property_key == key)
            .order_by(HfPropertyDefinition.version_no.desc())
            .limit(1)
        )

    @staticmethod
    async def media_sources(db, version_ids):
        if not version_ids:
            return []
        return (
            await db.execute(
                select(HfAssetVersion, HfAsset, HfStoredFile)
                .join(HfAsset, HfAsset.asset_id == HfAssetVersion.asset_id)
                .join(HfStoredFile, HfStoredFile.file_id == HfAssetVersion.file_id)
                .where(HfAssetVersion.version_id.in_(version_ids))
            )
        ).all()

    @staticmethod
    async def revisions(db, element_id, page_num, page_size):
        condition = HfElementRevision.element_id == element_id
        count = await db.scalar(select(func.count()).select_from(HfElementRevision).where(condition))
        rows = (
            await db.scalars(
                select(HfElementRevision)
                .where(condition)
                .order_by(HfElementRevision.revision_no.desc())
                .offset((page_num - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        return rows, count

    @staticmethod
    async def add(db, model, **values):
        row = model(**values)
        db.add(row)
        await db.flush()
        return row
