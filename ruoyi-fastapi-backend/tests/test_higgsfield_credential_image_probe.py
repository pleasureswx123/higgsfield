"""单张探针按能力编译，真实图片解码后才确认模型可用。"""
import base64
import io
import json
import unittest
from types import SimpleNamespace
from PIL import Image
from module_higgsfield.service.credential_test_image_probe_service import CredentialTestImageProbeService, UnsupportedCredentialProbe
from module_higgsfield.service.provider_http_service import ProviderHttpResult
from module_higgsfield.service.storage_service import StorageService


class CredentialImageProbeTests(unittest.TestCase):
    def binding(self, **changes):
        capabilities = {'parametersSchema': {'properties': {'n': {'type': 'integer', 'minimum': 1, 'maximum': 10}}},
                        'referenceRules': {'maxTotal': 0}, 'defaultParameters': {'n': 10}}
        values = dict(model_kind='image', config=SimpleNamespace(adapter_version='videoplus-v1'),
                      model_version=SimpleNamespace(gateway_alias='fixture-image', capabilities=capabilities))
        return SimpleNamespace(**(values | changes))

    def response(self, data=None, **changes):
        if data is None:
            handle = io.BytesIO()
            Image.new('RGB', (16, 16), 'blue').save(handle, format='PNG')
            data = handle.getvalue()
        inner = {'images': [{'b64_json': base64.b64encode(data).decode()}],
                 'output_format': 'png', 'size': '16x16'} | changes
        return ProviderHttpResult(transport='response', http_status=200,
            body={'id': 'probe-1', 'choices': [{'message': {'content': json.dumps(inner)}}]})

    def parse(self, response, max_pixels=1000):
        # 调用生产媒体校验实现，仅绕过无关的磁盘目录初始化。
        verifier = SimpleNamespace(policy=SimpleNamespace(max_pixels=max_pixels))
        return CredentialTestImageProbeService.parse(response, max_bytes=10000,
            verify_media=lambda handle: StorageService.verify_media(verifier, handle))

    def test_single_output_overrides_batch_default_and_rejects_other_probe(self):
        payload = CredentialTestImageProbeService.compile(self.binding())
        self.assertEqual(payload['n'], 1)
        self.assertEqual(payload['model'], 'fixture-image')
        for changes in ({'model_kind': 'video'}, {'model_version': None},
                        {'config': SimpleNamespace(adapter_version='unknown')}):
            with self.assertRaises(UnsupportedCredentialProbe):
                CredentialTestImageProbeService.compile(self.binding(**changes))
        binding = self.binding()
        binding.model_version.capabilities['parametersSchema']['properties']['n']['minimum'] = 2
        with self.assertRaises(UnsupportedCredentialProbe):
            CredentialTestImageProbeService.compile(binding)

    def test_verified_pixels_pass_without_fabricating_usage(self):
        result = self.parse(self.response())
        self.assertTrue(result.diagnostic.model_verified)
        self.assertEqual(result.diagnostic.output_count, 1)
        self.assertEqual(result.image_fact.usage, {})
        self.assertNotIn('b64_json', str(result.diagnostic.model_dump()))

    def test_invalid_pixels_mismatch_and_limits_never_pass(self):
        for response in (self.response(b'not-an-image'), self.response(b'\x89PNG\r\n\x1a\ncorrupt'),
                         self.response(size='32x32'), self.response(output_format='jpeg'), self.response(output_format='exe'),
                         ProviderHttpResult(transport='response', http_status=200, body={'ok': True})):
            self.assertFalse(self.parse(response).diagnostic.model_verified)
        self.assertFalse(self.parse(self.response(), max_pixels=1).diagnostic.model_verified)

    def test_auth_rejection_and_transport_unknown_are_distinct(self):
        rejected = self.parse(ProviderHttpResult(transport='response', http_status=401, body={'error': 'secret'}))
        self.assertEqual(rejected.diagnostic.issue, 'AUTH_REJECTED')
        unknown = self.parse(ProviderHttpResult(transport='timeout'))
        self.assertEqual(unknown.diagnostic.acceptance, 'unknown')
        self.assertFalse(unknown.diagnostic.model_verified)
        error = self.parse(ProviderHttpResult(transport='response', http_status=500, body={}))
        self.assertEqual(error.diagnostic.acceptance, 'unknown')
