"""固定元素引用的只读更新检查，不自动替换草稿或历史任务。"""
from exceptions.exception import PermissionException
from module_higgsfield.dao.element_dao import ElementDao
from module_higgsfield.dao.folder_dao import FolderDao
from module_higgsfield.entity.vo.reference_vo import ReferenceQuery
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.reference_service import ReferenceService


class ReferenceUpdateService:
    @staticmethod
    async def check(db, user, payload):
        project_id = int(payload.project_id)
        await WorkspaceService.authorize(db, user, project_id, 'generation:create')
        space = await FolderDao.space(db, project_id)
        items = []
        for identity in dict.fromkeys(payload.element_revision_ids):
            item = {'elementRevisionId': identity, 'state': 'unavailable'}
            revision = await ElementDao.revision(db, int(identity))
            element = await ElementDao.element(db, revision.element_id) if revision else None
            if element and element.space_id == space.space_id and element.del_flag == '0':
                try:
                    await WorkspaceService.authorize(db, user, project_id, 'element:read', owner_id=element.create_user_id)
                    result = await ReferenceService.search(db, user, ReferenceQuery(
                        projectId=payload.project_id, kind='element', elementId=str(element.element_id), pageSize=1,
                    ))
                except PermissionException:
                    pass
                else:
                    if result.rows:
                        candidate = result.rows[0]
                        item['state'] = 'current' if candidate['elementRevisionId'] == identity else 'updated'
                        if item['state'] == 'updated':
                            item['candidate'] = candidate
            items.append(item)
        return {'items': items}
