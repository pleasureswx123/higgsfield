"""价格来源列表仍遵循价格读取授权，不因接入助手放宽范围。"""

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from module_higgsfield.entity.vo.price_vo import PriceSourceQuery
from module_higgsfield.service.price_source_service import PriceSourceService


class PriceSourceListingTests(unittest.IsolatedAsyncioTestCase):
    async def test_authorization_precedes_database_read(self):
        with (
            patch('module_higgsfield.service.price_source_service.AdminScopeService.global_access',
                  new=AsyncMock(side_effect=PermissionError('无价格读取权限'))),
            patch('module_higgsfield.service.price_source_service.PriceSourceDao.page', new_callable=AsyncMock) as page,
        ):
            with self.assertRaises(PermissionError):
                await PriceSourceService.listing(None, None, PriceSourceQuery())
        page.assert_not_awaited()

    async def test_existing_source_id_and_evidence_are_returned_with_pagination(self):
        row = SimpleNamespace(source_id=1, source_type='manual_confirmation', source_url=None,
            excerpt='mm-imagen2 输入5美元，输出30美元，每百万Token', observed_time=datetime.now(timezone.utc))
        with (
            patch('module_higgsfield.service.price_source_service.AdminScopeService.global_access', new_callable=AsyncMock) as access,
            patch('module_higgsfield.service.price_source_service.PriceSourceDao.page', new=AsyncMock(return_value=([row], 3))),
        ):
            result = await PriceSourceService.listing(None, 'actor', PriceSourceQuery(page_size=1))
        access.assert_awaited_once_with(None, 'actor', 'billing:price:read')
        self.assertEqual(result.rows[0]['id'], '1')
        self.assertEqual(result.rows[0]['excerpt'], row.excerpt)
        self.assertEqual(result.total, 3)
        self.assertTrue(result.has_next)
