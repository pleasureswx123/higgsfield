"""生成目标只保存身份，读取时重新投影当前授权名称。"""

from exceptions.exception import PermissionException, ServiceWarning
from module_higgsfield.service.element_service import ElementService
from module_higgsfield.service.project_workspace_service import WorkspaceService


class GenerationTargetService:
    @staticmethod
    async def validate(db, user, project_id: int, element_id: str) -> dict:
        element, project, _ = await ElementService.authorized(db, user, int(element_id), 'element:read')
        if project.project_id != project_id:
            WorkspaceService.conflict('GENERATION_TARGET_UNAVAILABLE', '目标元素不存在或不属于当前项目')
        await WorkspaceService.authorize(db, user, project_id, 'element:edit', write=True, owner_id=element.create_user_id)
        await WorkspaceService.authorize(db, user, project_id, 'asset:create', write=True, owner_id=user.user.user_id)
        return {'id': str(element.element_id), 'projectId': str(project_id), 'name': element.element_name}

    @classmethod
    async def project(cls, db, user, job) -> dict | None:
        identity = (job.input_snapshot or {}).get('targetElementId')
        if not isinstance(identity, str) or not identity.isascii() or not identity.isdigit() or not 0 < int(identity) < 2**63:
            return None
        try:
            return await cls.validate(db, user, job.project_id, identity)
        except (PermissionException, ServiceWarning):
            # 任务可读不等于目标可读，失权时不泄露历史目标身份和名称。
            return None
