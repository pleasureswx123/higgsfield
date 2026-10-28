"""管理调用证据按字段和取值白名单投影，拒绝原始正文及秘密地址。"""
import re
from common.vo import PageModel
from module_higgsfield.dao.provider_call_read_dao import ProviderCallReadDao, STATES
from module_higgsfield.service.admin_scope_service import AdminScopeService
from module_higgsfield.service.project_workspace_service import WorkspaceService


class ProviderCallReadService:
    @staticmethod
    def safe_code(value):
        return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', value) else None

    @classmethod
    def metadata(cls, value):
        if not isinstance(value, dict):
            return {}
        result = {}
        # 不递归透传未知结构，未来适配器字段必须显式审查后加入。
        for key in ('connectionVersionId', 'modelVersionId', 'fencingToken', 'submissionCallId', 'recoveredEvidenceId'):
            item = value.get(key)
            if isinstance(item, str) and re.fullmatch(r'[0-9]{1,19}', item):
                result[key] = item
        for key in ('adapterVersion', 'mode', 'acceptance', 'transport', 'businessCode', 'recoveryReason', 'issue', 'state'):
            item = cls.safe_code(value.get(key))
            if item is not None:
                result[key] = item
        for key in ('outputCount', 'byteSize', 'httpStatus'):
            item = value.get(key)
            if type(item) is int and 0 <= item <= 9007199254740991:
                result[key] = item
        return result

    @classmethod
    def summary(cls, row):
        return {'id': str(row.call_id), 'jobId': str(row.job_id) if row.job_id is not None else None,
                'costCenterId': str(row.cost_center_id) if row.cost_center_id is not None else None,
                'operation': row.operation, 'state': next(key for key, value in STATES.items() if value == row.state),
                'acceptance': row.acceptance, 'httpStatus': row.http_status,
                'businessCode': cls.safe_code(row.business_code),
                'startedAt': row.started_time.isoformat() if row.started_time else None,
                'finishedAt': row.finished_time.isoformat() if row.finished_time else None}

    @classmethod
    async def listing(cls, db, user, query):
        actor, roles = await AdminScopeService.context(db, user, 'operations:read')
        rows, total = await ProviderCallReadDao.page(db, query, actor, roles)
        return PageModel(rows=[cls.summary(row) for row in rows], total=total,
                         pageNum=query.page_num, pageSize=query.page_size,
                         hasNext=query.page_num * query.page_size < total)

    @classmethod
    async def detail(cls, db, user, identity):
        actor, roles = await AdminScopeService.context(db, user, 'operations:read')
        row = await ProviderCallReadDao.detail(db, identity, actor, roles)
        if row is None:
            WorkspaceService.conflict('RESOURCE_NOT_FOUND', '调用记录不存在或不在管理范围内')
        return cls.summary(row) | {'requestMetadata': cls.metadata(row.request_metadata),
                                   'responseMetadata': cls.metadata(row.response_metadata)}
