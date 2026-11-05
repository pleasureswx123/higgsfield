"""工作器生命周期内复用连接；请求客户端独立，避免跨账号复用Cookie。"""
from contextlib import asynccontextmanager
from contextvars import ContextVar
import httpx

_pool = ContextVar('provider_connection_pool', default=None)


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
    return BorrowedTransport(pool) if pool is not None else None


@asynccontextmanager
async def provider_pool_scope(capacity):
    async with httpx.AsyncHTTPTransport(
        retries=0, trust_env=False,
        limits=httpx.Limits(max_connections=capacity, max_keepalive_connections=capacity, keepalive_expiry=30),
    ) as pool:
        token = _pool.set(pool)
        try:
            yield
        finally:
            _pool.reset(token)
