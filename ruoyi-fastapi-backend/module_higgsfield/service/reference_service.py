"""候选检索只提供当前可用引用，正式生成仍须再次校验。"""

from common.vo import PageModel
from module_higgsfield.dao.reference_dao import ReferenceDao
from module_higgsfield.dao.folder_dao import FolderDao
from module_higgsfield.dao.project_workspace_dao import WorkspaceDao
from module_higgsfield.service.project_workspace_service import WorkspaceService


class ReferenceService:
    @classmethod
    async def search(cls, db, user, query):
        project_id = int(query.project_id)
        project, role, _ = await WorkspaceService.authorize(db, user, project_id, 'generation:create')
        if project.status != '0':
            WorkspaceService.conflict('PROJECT_READ_ONLY', '当前项目不能创建生成引用')
        scopes = await WorkspaceDao.permission_scopes(db, role)
        if '*:*:*' not in user.permissions:
            scopes = {code: scope for code, scope in scopes.items() if code in user.permissions}
        space = await FolderDao.space(db, project_id)
        rows, total = await ReferenceDao.search(db, space.space_id, user.user.user_id, scopes, query)
        media = await ReferenceDao.revision_media(db, [row['version_id'] for row in rows if row['kind'] == 'element'])
        grouped = {}
        for item in media:
            grouped.setdefault(item.element_revision_id, []).append(item)
        items = []
        for row in rows:
            item = {
                'kind': row['kind'],
                'id': str(row['id']),
                'displayName': row['name'],
                'projectId': str(project_id),
                'allowedMediaRoles': {
                    'image': ['reference_image', 'first_frame'],
                    'video': ['reference_video'],
                }.get(row['media_type'], []),
            }
            if row['kind'] == 'asset':
                item['assetVersionIds'] = [str(row['version_id'])]
            else:
                selected = grouped[row['version_id']]
                item['elementRevisionId'] = str(row['version_id'])
                item['assetVersionIds'] = [str(value.asset_version_id) for value in selected]
                item['primaryAssetVersionId'] = next(
                    (str(value.asset_version_id) for value in selected if value.is_primary == 'Y'), None
                )
            items.append(item)
        return PageModel(
            rows=items,
            total=total,
            pageNum=query.page_num,
            pageSize=query.page_size,
            hasNext=query.page_num * query.page_size < total,
        )
