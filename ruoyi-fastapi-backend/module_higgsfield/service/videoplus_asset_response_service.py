"""解析素材注册与查询结果；人物生成引用始终保留素材 ID。"""

import re


class VideoPlusAssetResponseService:
    @staticmethod
    def _success(http_status: int, body: object) -> dict:
        if not 200 <= http_status < 300 or not isinstance(body, dict):
            raise ValueError('素材接口响应无效')
        base = body.get('base_resp')
        if not isinstance(base, dict) or type(base.get('status_code')) is not int or base['status_code'] != 0:
            raise ValueError('素材接口未返回业务成功')
        return body

    @classmethod
    def registration(cls, http_status: int, body: object) -> str:
        identity = cls._success(http_status, body).get('Id')
        if not isinstance(identity, str) or not re.fullmatch(r'asset-[A-Za-z0-9_-]{1,128}', identity):
            raise ValueError('素材注册未返回有效 Id')
        return identity

    @classmethod
    def status(cls, http_status: int, body: object, *, expected_id: str, expected_type: str = 'Image') -> str:
        identity = cls.registration(http_status, body)
        if identity != expected_id or body.get('AssetType') != expected_type:
            raise ValueError('查询返回的素材身份或类型不一致')
        state = body.get('Status')
        if state not in {'Active', 'Processing', 'Failed'}:
            raise ValueError('素材状态未知')
        return state

    @classmethod
    def reference(cls, http_status: int, body: object, *, expected_id: str) -> str:
        if cls.status(http_status, body, expected_id=expected_id) != 'Active':
            raise ValueError('人物素材尚未可用，不能提交生成')
        # 查询结果 URL 是下载地址，不能替换人物生成所需的 asset:// 引用。
        return 'asset://' + expected_id
