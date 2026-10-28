"""目录可用性区分已知阻断与待预检，不宣称完整生成可用。"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from exceptions.exception import ServiceWarning
from module_higgsfield.service.model_catalog_service import ModelCatalogService
from module_higgsfield.service.generation_policy_service import GenerationPolicyService

class CatalogAvailabilityTests(unittest.TestCase):
    def test_known_blocks_and_preflight_required(self):
        project = SimpleNamespace(status='0')
        config = SimpleNamespace(estimate_policy=object())
        self.assertEqual(ModelCatalogService.availability(project, config, True), {'available': False, 'reasonCode': 'GENERATION_PREFLIGHT_REQUIRED'})
        self.assertEqual(ModelCatalogService.availability(project, config, False)['reasonCode'], 'GENERATION_POLICY_UNAVAILABLE')
        config.estimate_policy = None
        self.assertEqual(ModelCatalogService.availability(project, config, True)['reasonCode'], 'GENERATION_ESTIMATE_UNAVAILABLE')
        project.status = '1'
        self.assertEqual(ModelCatalogService.availability(project, config, False)['reasonCode'], 'PROJECT_READ_ONLY')

    def test_runtime_requires_both_policy_and_signing(self):
        with patch.object(GenerationPolicyService, 'configured', return_value=object()), patch.object(GenerationPolicyService, 'tokens', return_value=object()):
            self.assertTrue(ModelCatalogService.runtime_ready())
        with patch.object(GenerationPolicyService, 'configured', return_value=object()), patch.object(GenerationPolicyService, 'tokens', side_effect=ServiceWarning(message='密钥不可用')):
            self.assertFalse(ModelCatalogService.runtime_ready())
