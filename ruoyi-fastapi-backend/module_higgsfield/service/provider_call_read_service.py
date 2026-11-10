"""按管理范围读取发送时脱敏快照；历史缺失不重建，秘密地址不返回。"""
import re
from module_higgsfield.service.provider_exchange_service import ProviderExchangeService
from common.vo import PageModel
from module_higgsfield.dao.provider_call_read_dao import ProviderCallReadDao, STATES
from module_higgsfield.service.admin_scope_service import AdminScopeService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.videoplus_asset_response_service import VideoPlusAssetResponseService


class ProviderCallReadService:
    @classmethod
    def asset_query(cls, row):
        """只依据本次已保存响应展示状态，不以 HTTP 200 或当前注册缓存推断。"""
        if row.operation not in {'asset_get', 'upload', 'register'}:
            return None
        metadata = getattr(row, 'asset_evidence', None) or {}
        exchanges = metadata.get('exchanges', {})
        entries = [item for item in exchanges.values() if isinstance(item, dict)] if isinstance(exchanges, dict) else []
        latest = max(entries, key=lambda item: str(item.get('startedAt', '')), default={})
        request = latest.get('request') or {}
        body = request.get('body') if isinstance(request, dict) else None
        identity = body.get('Id') if isinstance(body, dict) else None
        response = latest.get('response')
        state = None
        try:
            state = VideoPlusAssetResponseService.status(latest.get('httpStatus') or row.http_status or 0,
                response, expected_id=identity)
        except (ValueError, TypeError):
            pass
        if row.operation == 'register':
            state = None
            try:
                identity = VideoPlusAssetResponseService.registration(latest.get('httpStatus') or row.http_status or 0, response)
                state = 'Registered'
            except (ValueError, TypeError):
                pass
        elif row.operation == 'upload':
            # 使用当时经过上传解析器校验的结果，过期的临时地址不改变历史上传成功事实。
            result = getattr(row, 'upload_result', None) or {}
            state = None
            if (row.state == '2' and row.acceptance == 'not_applicable' and 200 <= (row.http_status or 0) < 300
                    and type(result.get('byteSize')) is int and str(result['byteSize']) == str(metadata.get('byteSize'))
                    and result.get('contentType') == metadata.get('mimeType') and result.get('expiresAt')):
                state = 'Uploaded'
        if row.operation in {'upload', 'register'} and state is None:
            if row.state == '0':
                state = 'Pending'
            elif row.state == '1':
                state = 'Sending'
            elif row.http_status is not None and row.http_status >= 400:
                state = 'RequestFailed'
        name = getattr(row, 'asset_name', None)
        if not name:
            # 供应商名称仅在身份和业务成功均已核验时作为后备。
            name = response.get('Name') if state and isinstance(response, dict) else None
            suffix = identity if isinstance(identity, str) and re.fullmatch(r'asset-[A-Za-z0-9_-]{1,128}', identity) else metadata.get('assetVersionId')
            name = f'{name or "参考素材"}（{suffix}）' if suffix else '参考素材（名称未记录）'
        return {'name': ProviderExchangeService.redact(str(name))[:250], 'state': state}

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
                'callerId': str(row.caller_id) if row.caller_id is not None else None,
                'callerUsername': row.caller_username, 'callerName': row.caller_name,
                'costCenterId': str(row.cost_center_id) if row.cost_center_id is not None else None,
                'operation': row.operation, 'state': next(key for key, value in STATES.items() if value == row.state),
                'acceptance': row.acceptance, 'httpStatus': row.http_status, 'assetQuery': cls.asset_query(row),
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
    async def tasks(cls, db, user, query):
        actor, roles = await AdminScopeService.context(db, user, 'operations:read')
        rows, total = await ProviderCallReadDao.tasks(db, query, actor, roles)
        return PageModel(rows=[{
            'id': str(row.job_id), 'projectId': str(row.project_id), 'kind': row.kind,
            'callerId': str(row.caller_id) if row.caller_id is not None else None,
            'callerName': row.caller_name, 'callerUsername': row.caller_username,
            'orchestrationState': row.orchestration_state, 'upstreamState': row.upstream_state,
            'createdAt': row.create_time.isoformat(),
            'finishedAt': row.finished_time.isoformat() if row.finished_time else None,
            'callCount': row.call_count, 'pollCount': row.poll_count,
        } for row in rows], total=total, pageNum=query.page_num, pageSize=query.page_size,
            hasNext=query.page_num * query.page_size < total)

    @classmethod
    async def process(cls, db, user, identity):
        actor, roles = await AdminScopeService.context(db, user, 'operations:read')
        rows = await ProviderCallReadDao.process(db, identity, actor, roles)
        if not rows:
            WorkspaceService.conflict('RESOURCE_NOT_FOUND', '任务调用记录不存在或不在管理范围内')
        return [cls.summary(row) for row in rows]

    @classmethod
    async def detail(cls, db, user, identity):
        actor, roles = await AdminScopeService.context(db, user, 'operations:read')
        row = await ProviderCallReadDao.detail(db, identity, actor, roles)
        if row is None:
            WorkspaceService.conflict('RESOURCE_NOT_FOUND', '调用记录不存在或不在管理范围内')
        exchanges = list((row.request_metadata or {}).get('exchanges', {}).values())
        exchanges.sort(key=lambda item: item['startedAt'])
        for item in exchanges:
            item['curl'] = ProviderExchangeService.curl(item['request'])
        task = await ProviderCallReadDao.task(db, row.job_id) if row.job_id else None
        task_view = None
        if task:
            snapshot = task.input_snapshot or {}
            assets = await ProviderCallReadDao.task_assets(db, task.job_id)
            task_view = {'id': str(task.job_id), 'projectId': str(task.project_id),
                         'actorId': str(task.actor_id) if task.actor_id != 1 else None, 'kind': task.kind,
                         'modelVersionId': str(task.model_version_id),
                         'referenceNames': ProviderExchangeService.redact({str(item.asset_version_id): item.asset_name for item in assets}),
                         'createdAt': task.create_time.isoformat(),
                         'orchestrationState': task.orchestration_state, 'upstreamState': task.upstream_state,
                         'input': ProviderExchangeService.redact({key: snapshot[key] for key in
                             ('prompt', 'parameters', 'references', 'folderId') if key in snapshot})}
        return cls.summary(row) | {'task': task_view, 'exchanges': exchanges, 'requestSource': 'saved' if exchanges else 'unavailable', 'requestMetadata': cls.metadata(row.request_metadata),
                                   'responseMetadata': cls.metadata(row.response_metadata)}
