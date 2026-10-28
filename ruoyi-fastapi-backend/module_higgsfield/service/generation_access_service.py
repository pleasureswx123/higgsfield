"""新外部调用意图共用的项目和执行用户授权检查。"""

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
        if not await GenerationActorDao.system_access(db, job.actor_id):
            WorkspaceService.conflict('GENERATION_FUNCTION_REVOKED', '原执行用户的系统生成功能授权已撤回，不能创建新的供应商调用')
