"""准备异常分类不允许任意错误文本进入审计。"""
import unittest
from exceptions.exception import ServiceWarning
from module_higgsfield.service.preparation_diagnostic_service import PreparationDiagnosticService as Service


class PreparationDiagnosticTests(unittest.TestCase):
    def test_classification_is_closed_and_never_returns_exception_text(self):
        self.assertEqual(Service.classify(TimeoutError('secret-key')), 'PREPARATION_TIMEOUT')
        self.assertEqual(Service.classify(RuntimeError('secret-key')), 'PREPARATION_FAILED')
        self.assertEqual(Service.classify(ServiceWarning(message='secret-key', data={'errorCode': 'PROVIDER_BINDING_INVALID'})), 'PROVIDER_BINDING_INVALID')
        for code in ('secret-key', ['PROVIDER_BINDING_INVALID'], None):
            self.assertEqual(Service.classify(ServiceWarning(message='secret-key', data={'errorCode': code})), 'PREPARATION_FAILED')
