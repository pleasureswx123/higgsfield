"""短事务写接口的幂等结果保存，调用方负责先授权与串行锁。"""

import json
from datetime import timedelta
from hashlib import sha256

from module_higgsfield.dao.project_dao import ProjectDao
from module_higgsfield.dao.project_workspace_dao import WorkspaceDao
from module_higgsfield.service.project_workspace_service import WorkspaceService
from utils.response_util import ResponseUtil
from utils.time_util import TimezoneUtil


class WriteService:
    @staticmethod
    async def lock(db, user, path, key, api_prefix='/api/v1'):
        if key and not await WorkspaceDao.lock_request(db, user.user.user_id, path, key, api_prefix):
            WorkspaceService.conflict('IDEMPOTENCY_IN_PROGRESS', '同一请求正在处理，请稍后重试')

    @staticmethod
    def digest(payload):
        return sha256(
            json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
        ).hexdigest()

    @staticmethod
    def audit(user):
        now = TimezoneUtil.utc_now()
        return {
            'create_by': user.user.user_name,
            'update_by': user.user.user_name,
            'create_time': now,
            'update_time': now,
        }

    @classmethod
    async def replay(cls, db, user, path, key, payload, method='POST', api_prefix='/api/v1'):
        row = await WorkspaceDao.replay(db, user.user.user_id, method, path, key, api_prefix) if key else None
        if row:
            if row.request_hash != cls.digest(payload):
                WorkspaceService.conflict('IDEMPOTENCY_KEY_REUSED', '请求标识已用于不同内容')
            if row.state != '1':
                WorkspaceService.conflict('IDEMPOTENCY_IN_PROGRESS', '请求尚未完成')
            return row.safe_result
        return None

    @classmethod
    async def finish(cls, db, user, path, key, payload, data, kind, result_id, method='POST', api_prefix='/api/v1'):
        response = json.loads(ResponseUtil.success(data=data).body)
        if key:
            audit = cls.audit(user)
            await ProjectDao.save_idempotency(
                db,
                actor_id=user.user.user_id,
                api_prefix=api_prefix,
                http_method=method,
                normalized_path=path,
                idempotency_key=key,
                request_hash=cls.digest(payload),
                state='1',
                http_status=200,
                result_type=kind,
                result_id=str(result_id),
                safe_result=response,
                expires_time=audit['create_time'] + timedelta(days=1),
                completed_time=audit['create_time'],
                fencing_token=1,
                **audit,
            )
        await db.commit()
        return response, False
