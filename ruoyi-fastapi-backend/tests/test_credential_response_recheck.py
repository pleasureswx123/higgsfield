"""复核只接受绑定完整的原响应，验证不产生新供应商调用。"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from tests.test_higgsfield_credential_image_probe import CredentialImageProbeTests
from module_higgsfield.service import credential_test_recheck_service as target


class CredentialResponseRecheckTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.before = dict(issue='RESPONSE_INVALID', transport='response', httpStatus=200)
        self.test = SimpleNamespace(test_id=1, state='2', model_version_id=1, result=self.before,
            provider_call_id=2, credential_version_id=3, cost_center_id=4, requested_by=5, config_hash='hash')
        self.call = SimpleNamespace(call_id=2, state='2', operation='test', job_id=None,
            credential_version_id=3, cost_center_id=4, actor_id=5, http_status=200,
            request_metadata={'testId': '1', 'configHash': 'hash'}, response_metadata=self.before)
        self.evidence = SimpleNamespace(provider_call_id=2, http_status=200,
            storage_key='provider-evidence/fixture', sha256='a'*64, byte_size=200)

    def test_rejects_mismatched_identity_and_terminal_success(self):
        eligible = target.CredentialTestRecheckService.eligible
        self.assertTrue(eligible(self.test, self.call, self.evidence))
        for obj, key, value in [(self.call, 'actor_id', 6), (self.test, 'state', '1'),
                                (self.evidence, 'provider_call_id', 9), (self.call, 'http_status', 500)]:
            old = getattr(obj, key)
            setattr(obj, key, value)
            self.assertFalse(eligible(self.test, self.call, self.evidence))
            setattr(obj, key, old)

    async def test_saved_response_recheck_keeps_original_in_audit(self):
        probe = CredentialImageProbeTests()
        result = probe.parse(probe.response(output_format=None, size=None))
        db = AsyncMock()
        db.__aenter__.return_value = db
        evidence_storage = SimpleNamespace(load=AsyncMock(return_value={}))
        with patch.object(target.CredentialTestDao, 'locked', AsyncMock(return_value=self.test)), \
             patch.object(target.ProviderCallDao, 'locked', AsyncMock(return_value=self.call)), \
             patch.object(target.CredentialTestResponseDao, 'get', AsyncMock(return_value=self.evidence)), \
             patch.object(target.JobLeaseDao, 'now', AsyncMock(return_value='now')), \
             patch.object(target.PriceSourceDao, 'audit', AsyncMock()) as audit, \
             patch.object(target.CredentialTestImageProbeService, 'parse', return_value=result):
            storage = SimpleNamespace(verify_media=lambda handle: {})
            args = (lambda: db, storage, evidence_storage)
            await target.CredentialTestRecheckService.recheck(*args, test_id=1, max_bytes=10000)
            self.assertEqual(self.test.state, '2')
            audit.assert_not_awaited()
            await target.CredentialTestRecheckService.recheck(*args, test_id=1, max_bytes=10000, apply=True)
            self.assertEqual(self.test.state, '1')
            self.assertEqual(self.call.acceptance, 'accepted')
            self.assertEqual(audit.call_args.args[1]['before_after']['before'], self.before)
            self.assertEqual(audit.await_count, 1)
            self.assertEqual(db.commit.await_count, 1)
