"""脱敏展示与服务状态测试，不发送供应商请求。"""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from module_higgsfield.service.credential_test_detail_service import CredentialTestDetailService as Detail
from module_higgsfield.service.credential_test_runtime_service import CredentialTestRuntimeService as Runtime
from module_higgsfield.service.storage_service import StorageService
from tests import test_higgsfield_credential_image_probe as probes


class DetailTests(unittest.TestCase):
    def test_saved_null_metadata_image_has_preview_usage_and_no_base64_dump(self):
        response = probes.CredentialImageProbeTests().response(output_format=None, size=None,
            usage={'input_tokens': 16, 'output_tokens': 7024})
        storage = SimpleNamespace(verify_media=lambda handle: StorageService.verify_media(
            SimpleNamespace(policy=SimpleNamespace(max_pixels=1000)), handle))
        detail = Detail.inspect(response.body, 200, storage, 10000)
        self.assertTrue(detail['currentValidation']['modelVerified'])
        self.assertTrue(detail['preview'].startswith('data:image/jpeg;base64,'))
        self.assertEqual(detail['usage']['input_tokens'], '16')
        self.assertEqual(detail['images'][0]['width'], 16)
        original = json.loads(response.body['choices'][0]['message']['content'])['images'][0]['b64_json']
        self.assertNotIn(original, json.dumps(detail['response']))

    def test_unknown_fields_and_plaintext_are_not_reflected(self):
        value = {'Authorization': 'Bearer PRIVATE', 'message': {'content': 'secret from gateway'},
                 'sk-private-key': 'anything', 'model': 'Bearer PRIVATE'}
        rendered = json.dumps(Detail.redact(value))
        for secret in ('PRIVATE', 'secret from gateway', 'sk-private-key', 'anything'):
            self.assertNotIn(secret, rendered)


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_preview_reuses_real_compiler_without_write_or_transport(self):
        from module_higgsfield.service.credential_test_binding_service import CredentialTestBindingService
        from module_higgsfield.service.admin_scope_service import AdminScopeService
        from module_higgsfield.service.credential_test_image_probe_service import CredentialTestImageProbeService
        binding = probes.CredentialImageProbeTests().binding()
        binding.config.base_url = 'https://gateway.example/'
        binding.version = SimpleNamespace(ciphertext='secret-not-for-response')
        db = AsyncMock()
        with patch.object(AdminScopeService, 'global_access', new=AsyncMock()), patch.object(CredentialTestBindingService, 'require', new=AsyncMock(return_value=binding)):
            result = await Detail.preview(db, object(), 1, 2, 3)
        self.assertEqual(result['request']['body'], CredentialTestImageProbeService.compile(binding))
        self.assertEqual(result['requestSource'], 'preview')
        self.assertIn('<YOUR_API_KEY>', result['curl'])
        self.assertNotIn('secret-not-for-response', json.dumps(result))
        db.commit.assert_not_awaited()
        db.add.assert_not_called()

    async def test_video_response_redacts_signed_url_and_keeps_task_usage(self):
        result = Detail.redact({'id': 'task-1', 'status': 'succeeded', 'content': {'video_url': 'https://media/?token=private'}, 'usage': {'completion_tokens': 1234}})
        self.assertEqual(result['usage']['completion_tokens'], 1234)
        self.assertNotIn('private', json.dumps(result))
        self.assertIn('video_url', result['content'])

    async def test_ready_requires_live_current_version_and_no_old_consumers(self):
        class Redis:
            def __init__(self, values): self.values = values
            async def scan_iter(self, **kwargs):
                for i in range(len(self.values)): yield i
            async def get(self, key): return json.dumps({'revision': self.values[key]})
        self.assertFalse((await Runtime.status(Redis([])))['ready'])
        self.assertTrue((await Runtime.status(Redis([Runtime.revision()])))['ready'])
        self.assertFalse((await Runtime.status(Redis([Runtime.revision(), 'old'])))['ready'])
