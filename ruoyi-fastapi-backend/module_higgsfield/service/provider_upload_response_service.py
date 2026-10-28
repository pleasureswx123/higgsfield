"""上传成功、文件身份与有效期限联合校验，不猜测默认24小时。"""

from datetime import datetime, timedelta

from module_higgsfield.entity.vo.provider_upload_vo import ProviderUploadedMedia
from utils.output_source_util import validate_output_source

HTTP_SUCCESS_START, HTTP_SUCCESS_END = 200, 300


class ProviderUploadResponseService:
    @staticmethod
    def parse(
        http_status: int,
        body: object,
        *,
        received_at: datetime,
        expected_size: int,
        expected_mime: str,
        safety_seconds: int = 60,
    ) -> ProviderUploadedMedia:
        if received_at.tzinfo is None or received_at.utcoffset() is None:
            raise ValueError('接收时间必须包含时区')
        if type(safety_seconds) is not int or safety_seconds < 0:
            raise ValueError('安全余量必须为非负整数')
        if (
            not HTTP_SUCCESS_START <= http_status < HTTP_SUCCESS_END
            or not isinstance(body, dict)
            or body.get('success') is not True
        ):
            raise ValueError('上传响应未证明成功')
        kind = expected_mime.split('/', maxsplit=1)[0]
        if (
            kind not in {'image', 'video'}
            or body.get('asset_type') != kind
            or body.get('content_type') != expected_mime
            or type(body.get('size')) is not int
            or body['size'] != expected_size
        ):
            raise ValueError('上传结果与原文件类型或大小不匹配')
        validate_output_source(body.get('url'))
        expires_at, issues = ProviderUploadResponseService._expiry(body, received_at, safety_seconds)
        return ProviderUploadedMedia(
            sourceUrl=body['url'],
            expiresAt=expires_at,
            fileName=body.get('file_name'),
            assetType=kind,
            contentType=expected_mime,
            byteSize=body['size'],
            issues=issues,
        )

    @staticmethod
    def _expiry(body: dict, received_at: datetime, safety_seconds: int) -> tuple[datetime, list[str]]:
        deadlines, issues = [], []
        for field in ('expires_at', 'expires_time'):
            if field not in body:
                continue
            try:
                deadline = datetime.fromisoformat(body[field])
                if deadline.tzinfo is None or deadline.utcoffset() is None:
                    raise ValueError('到期时间缺少时区')
                deadlines.append(deadline)
            except (TypeError, ValueError):
                issues.append('UPLOAD_EXPIRY_INVALID')
        if 'expires_in' in body:
            seconds = body['expires_in']
            if type(seconds) is int and seconds > 0:
                try:
                    deadlines.append(received_at + timedelta(seconds=seconds))
                except OverflowError:
                    issues.append('UPLOAD_EXPIRY_INVALID')
            else:
                issues.append('UPLOAD_EXPIRY_INVALID')
        if not deadlines:
            raise ValueError('上传响应缺少可用的到期证据')
        if len(set(deadlines)) > 1:
            issues.append('UPLOAD_EXPIRY_CONFLICT')
        expires_at = min(deadlines) - timedelta(seconds=safety_seconds)
        if expires_at <= received_at:
            raise ValueError('上传地址已过期或剩余有效期不足')
        return expires_at, issues
