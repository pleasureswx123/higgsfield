"""凭据专用校验边界，不将请求原文或校验异常输入返回客户端。"""

from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from utils.response_util import ResponseUtil


class CredentialRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request):
            try:
                return await original(request)
            except RequestValidationError:
                # errors() 中的 input 和 loc 均可能含密钥；只返回固定消息。
                response = ResponseUtil.failure(
                    msg='凭据请求格式无效，请检查必填字段、密钥格式与有效期',
                    dict_content={'code': 422, 'errorCode': 'CREDENTIAL_INPUT_INVALID'},
                )
                response.status_code = 422
                return response

        return handler
