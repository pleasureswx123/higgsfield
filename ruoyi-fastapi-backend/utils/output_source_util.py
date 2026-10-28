"""输出地址语法校验；实际下载还须执行独立的网络出口与重定向校验。"""

from urllib.parse import urlsplit


def validate_output_source(value):
    try:
        if not isinstance(value, str) or not 1 <= len(value) <= 16384:
            raise ValueError
        parts = urlsplit(value)
        if (
            parts.scheme != 'https'
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.fragment
            or any(ord(char) < 33 for char in value)
        ):
            raise ValueError
        _ = parts.port
    except (TypeError, ValueError):
        raise ValueError('输出源地址必须为有效的无用户凭据 HTTPS 地址') from None
