"""由前端互通测试调用，使用真实传输中间件和进程内防重放存储。"""
import asyncio
import base64
import json
import sys
from unittest.mock import patch

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from config.env import AppConfig, TransportCryptoConfig
from utils.log_util import logger
from middlewares.transport_crypto_middleware import TransportCryptoMiddleware
from utils.transport_crypto_util import TransportCryptoMonitorUtil, TransportKeyProvider


class ReplayStore:
    """只模拟 Redis SET NX；不将此测试当作真实 Redis 验收。"""

    def __init__(self):
        self.keys = set()

    async def set(self, key, value, *, ex, nx):
        assert ex > 0 and nx is True
        if key in self.keys:
            return False
        self.keys.add(key)
        return True


async def run(value):
    app = FastAPI()
    app.state.redis = ReplayStore()
    visits = []

    @app.post('/login')
    async def form_echo(request: Request):
        # 此端点只验证表单还原，并非真实账号密码验证。
        payload = dict(await request.form())
        visits.append('login')
        return {'code': 200, 'data': payload}

    @app.delete('/items')
    async def delete_echo(request: Request):
        visits.append('items')
        return JSONResponse({'code': 409, 'msg': '修订冲突', 'data': {
            'errorCode': 'REVISION_CONFLICT', 'ids': request.query_params.getlist('ids'),
            'body': await request.json(),
        }}, status_code=409)

    @app.put('/upload')
    async def upload_echo(request: Request):
        visits.append('upload')
        return {'code': 200, 'data': {'bytes': list(await request.body()),
                                     'part': request.query_params.get('part'),
                                     'range': request.headers.get('content-range')}}

    @app.get('/download')
    async def download_echo(request: Request):
        visits.append('download')
        if request.query_params.get('denied') == '1':
            return JSONResponse({'code': 401, 'msg': '下载权限失效'}, status_code=401)
        assert request.headers.get('range') == 'bytes=0-2'
        return Response(bytes([0, 255, 7]), status_code=206, media_type='application/octet-stream',
                        headers={'Content-Range': 'bytes 0-2/3'})

    @app.get('/events')
    async def events_echo(request: Request):
        visits.append('events')
        assert request.headers.get('last-event-id') == '42'
        assert request.query_params.get('limit') == '10'
        if request.query_params.get('denied') == '1':
            return JSONResponse({'code': 401, 'msg': '事件权限失效'}, status_code=401)
        async def events():
            yield 'id: 43\ndata: {"state":"running"}\n\n'
            yield 'id: 44\ndata: {"state":"succeeded"}\n\n'
        return StreamingResponse(events(), media_type='text/event-stream')

    app.add_middleware(TransportCryptoMiddleware)
    async def asgi(scope, receive, send):
        # 同时验证旧版断开监听与新版响应路径。
        scope['asgi'] = {**scope.get('asgi', {}), 'spec_version': value.get('asgiVersion', '2.3')}
        await app(scope, receive, send)

    responses = []
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=asgi), base_url='https://test') as client:
        for item in value['requests']:
            if item.get('disableReplayStore'):
                app.state.redis = None
            config = item['config']
            response = await client.request(config['method'], config['url'], params=config.get('params'),
                                            headers=config.get('headers'), content=(base64.b64decode(item['bodyBase64'])
                                            if 'bodyBase64' in item else config.get('data')))
            responses.append({'status': response.status_code, 'headers': dict(response.headers),
                              'data': response.json() if 'application/json' in response.headers.get('content-type', '') else None,
                              'bodyBase64': base64.b64encode(response.content).decode()})
    return {'responses': responses, 'visits': visits}


if __name__ == '__main__':
    logger.remove()
    logger.add(sys.stderr)
    value = json.load(sys.stdin)
    with (patch.object(TransportKeyProvider, 'get_private_key_pem', return_value=value['privateKey']),
          patch.object(TransportCryptoMonitorUtil, '_get_redis_client', return_value=None),
          patch.object(TransportCryptoConfig, 'transport_crypto_enabled', True),
          patch.object(TransportCryptoConfig, 'transport_crypto_mode', 'required'),
          patch.object(TransportCryptoConfig, 'transport_crypto_enabled_paths', ''),
          patch.object(TransportCryptoConfig, 'transport_crypto_exclude_paths', ''),
          patch.object(AppConfig, 'app_root_path', '')):
        print(json.dumps(asyncio.run(run(value)), ensure_ascii=False))
