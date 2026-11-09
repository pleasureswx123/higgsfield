"""使用脱敏样例验证素材状态与下一步参数，不调用供应商。"""

import unittest

from module_higgsfield.service.videoplus_asset_response_service import VideoPlusAssetResponseService as Parser


class AssetResponseTests(unittest.TestCase):
    def setUp(self):
        self.body = {'Id': 'asset-example-1', 'Status': 'Active', 'AssetType': 'Image',
                     'URL': 'https://example.com/temporary.png', 'base_resp': {'status_code': 0}}

    def test_active_uses_id_not_download_url(self):
        identity = Parser.registration(200, self.body)
        self.assertEqual(Parser.reference(200, self.body, expected_id=identity), 'asset://asset-example-1')

    def test_processing_and_failed_never_generate(self):
        for state in ('Processing', 'Failed', 'Expired', 'Deleted'):
            body = {**self.body, 'Status': state}
            self.assertEqual(Parser.status(200, body, expected_id='asset-example-1'), state)
            with self.assertRaises(ValueError):
                Parser.reference(200, body, expected_id='asset-example-1')

    def test_wrong_identity_type_status_and_business_error_rejected(self):
        for patch in ({'Id': 'asset-other'}, {'Id': 'asset-x/path'}, {'AssetType': 'Video'},
                      {'Status': 'unknown'}, {'base_resp': {'status_code': True}},
                      {'base_resp': {'status_code': 1}}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                Parser.reference(200, {**self.body, **patch}, expected_id='asset-example-1')
