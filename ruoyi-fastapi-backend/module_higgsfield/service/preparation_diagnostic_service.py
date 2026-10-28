"""仅记录准备异常的白名单类别，不保存异常正文。"""
from exceptions.exception import ServiceWarning
from module_higgsfield.dao.preparation_diagnostic_dao import PreparationDiagnosticDao
from module_higgsfield.dao.job_event_dao import JobEventDao


class PreparationDiagnosticService:
    MESSAGES = {
        'PROVIDER_BINDING_INVALID': '原任务的供应商账号与固定凭据绑定不完整，准备暂未完成。',
        'PROVIDER_CREDENTIAL_UNAVAILABLE': '原任务固定凭据或连接当前不可用，不会自动切换凭据。',
        'PROVIDER_ADAPTER_UNSUPPORTED': '固定模型或连接与当前适配器不兼容，准备暂未完成。',
        'PREPARATION_TIMEOUT': '本次准备处理超过等待时限，后台已安排后续处理。',
        'PREPARATION_FAILED': '本次准备处理发生异常，具体原因需管理员核查。',
    }

    @classmethod
    def classify(cls, error):
        if isinstance(error, TimeoutError):
            return 'PREPARATION_TIMEOUT'
        code = error.data.get('errorCode') if isinstance(error, ServiceWarning) and isinstance(error.data, dict) else None
        return code if isinstance(code, str) and code in cls.MESSAGES else 'PREPARATION_FAILED'

    @classmethod
    async def record(cls, db, job, now, worker, code):
        if code not in cls.MESSAGES:
            raise ValueError('准备诊断代码不在白名单中')
        if job.orchestration_state not in {'0', '1'}:
            return
        prior = await PreparationDiagnosticDao.latest(db, job)
        data = prior.before_after if prior else {}
        if data == {'code': code, 'revision': str(job.revision)}:
            return
        job.revision += 1
        job.event_sequence += 1
        job.update_time, job.update_by = now, worker
        await PreparationDiagnosticDao.add(db, job, now, worker, code)
        await JobEventDao.state(db, job, now, worker)

    @classmethod
    async def read(cls, db, job):
        if job.orchestration_state not in {'0', '1'}:
            return None
        row = await PreparationDiagnosticDao.latest(db, job)
        data = row.before_after if row and isinstance(row.before_after, dict) else {}
        code = data.get('code')
        if data.get('revision') != str(job.revision) or not isinstance(code, str) or code not in cls.MESSAGES:
            return None
        return {'code': code, 'phase': 'prepare', 'message': cls.MESSAGES[code]}
