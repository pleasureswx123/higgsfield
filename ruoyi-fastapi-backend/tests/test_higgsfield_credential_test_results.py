"""测试诊断不把HTTP成功当作模型通过，不泄漏历史原始载荷。"""
import unittest
from datetime import datetime, UTC
from types import SimpleNamespace
from pydantic import ValidationError
from module_higgsfield.entity.vo.credential_test_result_vo import CredentialTestResult
from module_higgsfield.service.credential_test_service import CredentialTestService


class CredentialTestResultTests(unittest.TestCase):
    def test_success_needs_accepted_result_evidence(self):
        values = dict(transport='response', authentication='passed', acceptance='accepted',
                      httpStatus=200, modelVerified=True, outputCount=1, issue='NONE')
        self.assertTrue(CredentialTestResult(**values).model_verified)
        for changes in ({'outputCount': 0}, {'acceptance': 'unknown'}, {'httpStatus': 500},
                        {'modelVerified': False}, {'outputCount': True}, {'response': {'Authorization': 'secret'}}):
            with self.assertRaises(ValidationError):
                CredentialTestResult(**(values | changes))

    def test_timeout_and_not_sent_are_distinct(self):
        values = dict(transport='timeout', authentication='unknown', acceptance='unknown', issue='TRANSPORT_UNKNOWN')
        self.assertEqual(CredentialTestResult(**values).acceptance, 'unknown')
        with self.assertRaises(ValidationError):
            CredentialTestResult(**(values | {'httpStatus': 200}))
        with self.assertRaises(ValidationError):
            CredentialTestResult(**(values | {'transport': 'not_sent'}))
        self.assertEqual(CredentialTestResult(transport='not_sent', authentication='unknown', acceptance='not_applicable', issue='PROBE_UNSUPPORTED').transport, 'not_sent')

    def test_result_projection_drops_invalid_historical_payload(self):
        row = SimpleNamespace(test_id=1, credential_version_id=2, connection_version_id=3, config_hash='a'*64,
            model_version_id=None, cost_center_id=4, requested_by=5, state='2', provider_call_id=None,
            finished_time=datetime.now(UTC), create_time=datetime.now(UTC), result={'Authorization': 'secret', 'url': 'https://private'})
        result = CredentialTestService.result(row)
        self.assertEqual(result['result'], {'issue': 'RESPONSE_INVALID'})
        self.assertNotIn('secret', str(result))
