"""只读测试证据：请求来源明确、密钥不返回、图片响应有界展示。"""
import asyncio
import base64
import io
import json
import shlex
from types import SimpleNamespace
from PIL import Image
from module_higgsfield.dao.credential_test_dao import CredentialTestDao
from module_higgsfield.dao.credential_test_response_dao import CredentialTestResponseDao
from module_higgsfield.dao.provider_call_dao import ProviderCallDao
from module_higgsfield.dao.provider_dao import ProviderDao
from module_higgsfield.dao.model_dao import ModelDao
from module_higgsfield.service.admin_scope_service import AdminScopeService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.image_worker_runtime import image_resources
from module_higgsfield.service.credential_test_response_crypto_service import CredentialTestResponseCryptoService
from module_higgsfield.service.provider_response_storage_service import ProviderResponseStorageService
from module_higgsfield.service.credential_test_image_probe_service import CredentialTestImageProbeService
from module_higgsfield.service.provider_http_service import ProviderHttpResult
from module_higgsfield.service.write_service import WriteService
from module_higgsfield.service.credential_test_service import CredentialTestService


class CredentialTestDetailService:
    @staticmethod
    def request_view(url, body=None, method='POST'):
        headers = {'Authorization': 'Bearer <YOUR_API_KEY>', 'X-Biz-Id': 'op',
                   'Content-Type': 'application/json', 'Accept': 'application/json', 'Accept-Encoding': 'identity'}
        request = {'method': method, 'url': url, 'headers': headers}
        curl = 'curl --request ' + method + ' ' + shlex.quote(url) + ''.join(
            ' --header ' + shlex.quote(key + ': ' + value) for key, value in headers.items())
        if body is not None:
            request['body'] = body
            curl += ' --data-raw ' + shlex.quote(json.dumps(body, ensure_ascii=False))
        return {'request': request, 'curl': curl}

    @classmethod
    async def preview(cls, db, user, version_id, model_version_id, cost_center_id):
        """只编译待发送内容；不解密密钥、不建立调用记录、不访问供应商。"""
        from module_higgsfield.service.credential_test_binding_service import CredentialTestBindingService
        await AdminScopeService.global_access(db, user, 'credential:read')
        binding = await CredentialTestBindingService.require(db, version_id, cost_center_id, model_version_id)
        try:
            body = CredentialTestImageProbeService.compile(binding)
        except ValueError:
            WorkspaceService.conflict('TEST_PREVIEW_UNAVAILABLE', '此模型配置暂不支持生成测试，请检查模型能力')
        result = cls.request_view(binding.config.base_url + 'v1/chat/completions', body)
        result['requestSource'] = 'preview'
        if binding.model_kind == 'video':
            result['pollPreview'] = cls.request_view(binding.config.base_url + 'v1/video/tasks/<TASK_ID>', method='GET')
        return result

    @staticmethod
    def redact(value, depth=0):
        """供应商任意扩展字段不直接回显；只展示协议内的白名单字段。"""
        if depth > 12:
            return '[已省略深层内容]'
        if isinstance(value, list):
            return [CredentialTestDetailService.redact(item, depth + 1) for item in value[:16]]
        if isinstance(value, dict):
            allowed = {'id', 'created', 'model', 'object', 'choices', 'index', 'message', 'role', 'content',
                       'finish_reason', 'images', 'b64_json', 'output_format', 'size', 'usage', 'input_tokens',
                       'output_tokens', 'total_tokens', 'prompt_tokens', 'completion_tokens', 'input_tokens_details',
                       'output_tokens_details', 'text_tokens', 'image_tokens', 'cached_tokens'}
            allowed.update({'task', 'status', 'resolution', 'duration', 'ratio', 'generate_audio', 'base_resp',
                            'status_code', 'status_msg', 'total_seconds', 'image_count', 'error', 'code'})
            result = {}
            for key, item in value.items():
                if key == 'b64_json':
                    result[key] = f'[图片 Base64 已省略，{len(item) if isinstance(item, str) else 0} 字符]'
                elif key == 'video_url':
                    result[key] = '[视频临时签名地址已脱敏；归档后可在下方播放]'
                elif key == 'content' and isinstance(item, str):
                    try:
                        result[key] = CredentialTestDetailService.redact(json.loads(item), depth + 1)
                    except (ValueError, RecursionError):
                        result[key] = f'[非 JSON 内容已省略，{len(item)} 字符]'
                elif key in allowed:
                    result[key] = CredentialTestDetailService.redact(item, depth + 1)
                else:
                    result['_omittedFields'] = True
            return result
        if isinstance(value, str):
            # 协议枚举和标识不应包含认证信息或长篇文本。
            if len(value) > 150 or 'bearer ' in value.lower() or 'sk-' in value.lower():
                return '[内容已脱敏]'
            return value
        return value if value is None or isinstance(value, (bool, int, float)) else '[已省略]'

    @staticmethod
    def inspect(body, status, storage, maximum):
        if isinstance(body, dict) and ('status' in body or 'task' in body):
            from module_higgsfield.service.videoplus_response_service import VideoPlusResponseService
            task = body.get('task', body)
            fact = VideoPlusResponseService.polling(status, body, expected_task_id=task.get('id', 'unknown'))
            return {'response': CredentialTestDetailService.redact(body), 'images': [], 'preview': None,
                    'usage': CredentialTestDetailService.redact(task.get('usage')), 'currentValidation': {'upstreamState': fact.upstream_state, 'issues': fact.issues}}
        parsed = CredentialTestImageProbeService.parse(ProviderHttpResult(transport='response', http_status=status, body=body),
            max_bytes=maximum, verify_media=storage.verify_media)
        images, preview = [], None
        fact = parsed.image_fact
        if fact:
            for item in fact.images:
                try:
                    data = item.data.get_secret_value()
                    metadata = storage.verify_media(io.BytesIO(data))
                    images.append(metadata)
                    if preview is None:
                        with Image.open(io.BytesIO(data)) as picture:
                            picture.thumbnail((512, 512))
                            out = io.BytesIO()
                            picture.convert('RGB').save(out, 'JPEG', quality=80)
                            preview = 'data:image/jpeg;base64,' + base64.b64encode(out.getvalue()).decode()
                except Exception:
                    images.append({'error': '图片实际解码或容量校验失败'})
        return {'response': CredentialTestDetailService.redact(body), 'images': images, 'preview': preview,
                'usage': fact.usage if fact else {}, 'issues': fact.issues if fact else ['RESPONSE_STRUCTURE_INVALID'],
                'currentValidation': parsed.diagnostic.model_dump(by_alias=True)}

    @classmethod
    async def get(cls, db, user, test_id):
        await AdminScopeService.global_access(db, user, 'credential:read')
        row = await CredentialTestDao.get(db, test_id)
        if row is None:
            WorkspaceService.conflict('RESOURCE_NOT_FOUND', '测试记录不存在')
        call = await ProviderCallDao.get(db, row.provider_call_id) if row.provider_call_id else None
        config = await ProviderDao.version(db, row.connection_version_id)
        version = await ModelDao.version(db, row.model_version_id) if row.model_version_id else None
        result = {'testId': str(test_id), 'testState': row.state, 'storedDiagnostic': CredentialTestService.result(row)['result'], 'requestSource': 'unavailable',
                  'httpStatus': call.http_status if call else None,
                  'startedAt': call.started_time.isoformat() if call and call.started_time else None,
                  'finishedAt': call.finished_time.isoformat() if call and call.finished_time else None}
        result['elapsedSeconds'] = round((call.finished_time - call.started_time).total_seconds(), 3) if call and call.finished_time and call.started_time else None
        from module_higgsfield.service.credential_test_cost_service import CredentialTestCostService
        cost = (await CredentialTestCostService.attach(db, user, [CredentialTestService.result(row)]))[0]
        result['billing'] = cost.get('cost')
        result['costVisibility'] = cost['costVisibility']
        snapshot = call.request_metadata.get('requestSnapshot') if call else None
        if call and call.request_metadata.get('videoTaskId'):
            result['taskId'] = call.request_metadata['videoTaskId']
            result['submissionHttpStatus'] = call.request_metadata.get('videoSubmissionHttpStatus')
            result['latestPoll'] = call.request_metadata.get('videoLatestPoll')
            result['pollRequest'] = {'method': 'GET', 'url': config.base_url + 'v1/video/tasks/' + call.request_metadata['videoTaskId'],
                                     'headers': {'Authorization': 'Bearer <YOUR_API_KEY>', 'X-Biz-Id': 'op',
                                                 'Content-Type': 'application/json', 'Accept': 'application/json', 'Accept-Encoding': 'identity'}}
            result['hasVideo'] = bool((call.response_metadata or {}).get('testVideoFile'))
            submission = call.request_metadata.get('videoSubmissionEvidence')
            if submission:
                storage, crypto, response, maximum = image_resources()
                saved = ProviderResponseStorageService(storage, CredentialTestResponseCryptoService(crypto.keyring), max_bytes=response.max_bytes)
                result['submissionResponse'] = cls.redact(await saved.load(submission, call.call_id, test_id))
        if snapshot:
            result['requestSource'] = 'saved'
        elif config and version:
            try:
                payload = CredentialTestImageProbeService.compile(SimpleNamespace(model_kind='image', config=config, model_version=version))
                if call and WriteService.digest(payload) == call.request_hash:
                    snapshot = {'url': config.base_url + 'v1/chat/completions', 'body': payload}
                    result['requestSource'] = 'reconstructed_hash_verified'
            except ValueError:
                pass
        if snapshot:
            result.update(cls.request_view(snapshot['url'], snapshot['body']))
        evidence = await CredentialTestResponseDao.get(db, test_id)
        if evidence:
            result['httpStatus'] = evidence.http_status
            storage, crypto, response, maximum = image_resources()
            saved = ProviderResponseStorageService(storage, CredentialTestResponseCryptoService(crypto.keyring), max_bytes=response.max_bytes)
            body = await saved.load({key: getattr(evidence, key) for key in ('storage_key', 'sha256', 'byte_size')}, evidence.provider_call_id, test_id)
            result.update(await asyncio.to_thread(cls.inspect, body, evidence.http_status, storage, maximum))
        else:
            result['evidenceMessage'] = '尚无保存的完整响应；仅显示已记录状态，不重发请求。'
        return result

    @staticmethod
    async def video(db, user, test_id):
        from fastapi.responses import StreamingResponse
        from module_higgsfield.service.storage_io_service import open_source
        from module_higgsfield.service.storage_service import StorageService
        await AdminScopeService.global_access(db, user, 'credential:read')
        test = await CredentialTestDao.get(db, test_id)
        call = await ProviderCallDao.get(db, test.provider_call_id) if test and test.provider_call_id else None
        media = (call.response_metadata or {}).get('testVideoFile') if call else None
        if not media:
            WorkspaceService.conflict('RESOURCE_NOT_FOUND', '测试视频尚未保存')
        storage = StorageService()
        async def stream():
            async with open_source(storage, media['storage_key']) as handle:
                while chunk := await asyncio.to_thread(handle.read, 65536):
                    yield chunk
        return StreamingResponse(stream(), media_type=media['mime_type'], headers={'Cache-Control': 'private, no-store'})
