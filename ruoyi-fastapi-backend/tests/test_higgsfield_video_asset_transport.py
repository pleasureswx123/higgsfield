"""仅验证素材接口编译，不发起外部请求。"""

import json
import unittest
from unittest.mock import AsyncMock

from module_higgsfield.service.provider_http_service import ProviderHttpService


class VideoAssetTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_register_and_get_use_exact_supplier_fields(self):
        transport = object.__new__(ProviderHttpService)
        transport._request = AsyncMock()
        await transport.register_asset('https://example.com/person.png', project='eva', asset_type='Image', name='人物')
        method, path, raw = transport._request.call_args.args
        self.assertEqual((method, path), ('POST', 'v1/mm/assets'))
        self.assertEqual(json.loads(raw), {'URL': 'https://example.com/person.png', 'AssetType': 'Image', 'ProjectName': 'eva', 'Name': '人物'})
        await transport.get_asset('asset-20261023155807-t6lpb')
        method, path, raw = transport._request.call_args.args
        self.assertEqual((method, path), ('POST', 'v1/mm/assets/get'))
        self.assertEqual(json.loads(raw), {'Id': 'asset-20261023155807-t6lpb'})

    async def test_invalid_registration_is_rejected_before_transport(self):
        transport = object.__new__(ProviderHttpService)
        transport._request = AsyncMock()
        for project, kind in [('default', 'Image'), ('eva', 'image')]:
            with self.assertRaises(ValueError):
                await transport.register_asset('https://example.com/person.png', project=project, asset_type=kind)
        with self.assertRaises(ValueError):
            await transport.get_asset('asset-good/../bad')
        transport._request.assert_not_called()
