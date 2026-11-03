"""新外部调用意图共用的项目和执行用户授权检查。"""

from module_higgsfield.dao.asset_dao import AssetDao
from module_higgsfield.dao.folder_dao import FolderDao
from module_higgsfield.dao.generation_actor_dao import GenerationActorDao
from module_higgsfield.dao.project_governance_dao import ProjectGovernanceDao
from module_higgsfield.service.project_workspace_service import WorkspaceService


class GenerationAccessService:
    @staticmethod
    async def require(db, job):
        # 调用方先锁任务，再锁项目；授权共享锁保持到意图事务提交。
        project = await ProjectGovernanceDao.locked(db, job.project_id)
        if project is None or project.del_flag != '0' or project.status != '0':
            WorkspaceService.conflict('PROJECT_READ_ONLY', '项目已暂停、归档或不可用，不能创建新的供应商调用')
        if not await GenerationActorDao.project_access(db, job.project_id, job.actor_id):
            WorkspaceService.conflict('GENERATION_ACTOR_UNAVAILABLE', '原执行用户已停用或项目生成授权已撤回，不能创建新的供应商调用')
        # Owner只要求平台基础访问；其他成员仍受系统生成功能授权限制。
        permission = 'project:read' if await GenerationActorDao.is_project_owner(db, job.project_id, job.actor_id) else 'generation:create'
        if not await GenerationActorDao.system_access(db, job.actor_id, permission):
            WorkspaceService.conflict('GENERATION_FUNCTION_REVOKED', '原执行用户的系统生成功能授权已撤回，不能创建新的供应商调用')
        # 排队期间可能发生素材删除或撤权，发送前再次验证固定引用。
        media = job.input_snapshot.get('compiled', {}).get('media', [])
        if media:
            space = await FolderDao.space(db, job.project_id)
            for item in media:
                version = await AssetDao.version(db, int(item['assetVersionId']))
                asset = await AssetDao.asset(db, version.asset_id) if version else None
                if (space is None or asset is None or asset.space_id != space.space_id
                        or asset.del_flag != '0' or str(version.file_id) != item['fileId']):
                    WorkspaceService.conflict('REFERENCE_UNAVAILABLE', '参考素材在排队期间已不可用')
                for code in ('asset:read', 'asset:reference'):
                    if not await GenerationActorDao.project_access(db, job.project_id, job.actor_id, code, asset.create_user_id):
                        WorkspaceService.conflict('REFERENCE_UNAVAILABLE', '参考素材权限已撤回')
