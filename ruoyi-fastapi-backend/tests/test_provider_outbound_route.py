"""出口配置严格按域名隔离，不依赖真实供应商。"""
import os
import unittest
from unittest.mock import AsyncMock, patch
import httpx
from module_higgsfield.service.provider_connection_pool import RoutedTransport, local_bindings


class ProviderOutboundRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_host_only_and_no_retry_fallback(self):
        with patch.dict(os.environ, {'HF_PROVIDER_LOCAL_BINDINGS':'{"images.example":"127.0.0.2"}'}):
            transport = RoutedTransport(2)
        bound, default = AsyncMock(), AsyncMock()
        bound.handle_async_request.side_effect = httpx.ConnectError('本机出口不可用')
        await transport.aclose()
        transport.transports = {'127.0.0.2':bound, None:default}
        with self.assertRaises(httpx.ConnectError):
            await transport.handle_async_request(httpx.Request('POST','https://images.example/v1/chat/completions'))
        bound.handle_async_request.assert_awaited_once()
        default.handle_async_request.assert_not_called()
        await transport.handle_async_request(httpx.Request('GET','https://other.images.example/'))
        default.handle_async_request.assert_awaited_once()
        await transport.aclose()
        bound.aclose.assert_awaited_once()
        default.aclose.assert_awaited_once()

    def test_invalid_configuration_fails_closed(self):
        for raw in ('[]','null','{"*.example":"127.0.0.1"}',
                    '{"images.example":"0.0.0.0"}', '{"images.example":"not-an-ip"}'):
            with self.subTest(raw=raw), patch.dict(os.environ, {'HF_PROVIDER_LOCAL_BINDINGS':raw}):
                with self.assertRaises(ValueError):
                    local_bindings()
