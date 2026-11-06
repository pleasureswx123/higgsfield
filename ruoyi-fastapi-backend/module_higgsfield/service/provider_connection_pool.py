"""工作器生命周期内复用连接；请求客户端独立，避免跨账号复用Cookie。"""
from contextlib import asynccontextmanager
from contextvars import ContextVar
import ipaddress
import json
import os
import re
import httpx

_pool = ContextVar('provider_connection_pool', default=None)


def local_bindings():
    """运维按精确供应商域名配置本机出口，不读取系统代理或改变全局路由。"""
    raw = os.getenv('HF_PROVIDER_LOCAL_BINDINGS', '{}')
    try:
        values = json.loads(raw)
        if not isinstance(values, dict) or len(values) > 32:
            raise ValueError
        result = {}
        for host, address in values.items():
            if not isinstance(host, str) or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', host):
                raise ValueError
            parsed = ipaddress.ip_address(address)
            if parsed.is_unspecified or parsed.is_multicast:
                raise ValueError
            result[host] = str(parsed)
        return result
    except (ValueError, TypeError):
        raise ValueError('供应商出口配置无效：须为精确小写域名到本机IP的JSON映射') from None


class RoutedTransport(httpx.AsyncBaseTransport):
    """固定域名绑定固定出口；出口不可用直接报错，绝不切换出口重发付费请求。"""
    def __init__(self, capacity):
        self.bindings = local_bindings()
        self.transports = {address: httpx.AsyncHTTPTransport(
            retries=0, trust_env=False, local_address=address,
            limits=httpx.Limits(max_connections=capacity, max_keepalive_connections=capacity, keepalive_expiry=30),
        ) for address in {None, *self.bindings.values()}}

    async def handle_async_request(self, request):
        return await self.transports[self.bindings.get(request.url.host)].handle_async_request(request)

    async def aclose(self):
        for transport in self.transports.values():
            await transport.aclose()


class BorrowedTransport(httpx.AsyncBaseTransport):
    def __init__(self, pool):
        self.pool = pool

    async def handle_async_request(self, request):
        return await self.pool.handle_async_request(request)

    async def aclose(self):
        # 连接池由工作器负责关闭，请求客户端不拥有它。
        pass


def request_transport():
    pool = _pool.get()
    return BorrowedTransport(pool) if pool is not None else RoutedTransport(100)


@asynccontextmanager
async def provider_pool_scope(capacity):
    async with RoutedTransport(capacity) as pool:
        token = _pool.set(pool)
        try:
            yield
        finally:
            _pool.reset(token)
