"""网络诊断仅记录白名单事实，不保存异常正文、密钥或任意响应头。"""
import re


def error_chain(error):
    """沿显式原因或上下文保留系统错误码，避免丢失 Windows 连接重置证据。"""
    result, seen = [], set()
    while error is not None and id(error) not in seen and len(result) < 8:
        seen.add(id(error))
        item = {'type': type(error).__name__}
        for name in ('errno', 'winerror'):
            value = getattr(error, name, None)
            if type(value) is int:
                item[name] = value
        result.append(item)
        error = error.__cause__ or error.__context__
    return result


def response_facts(response):
    """保留可关联供应商日志的调用编号及传输信息，排除额度和 Cookie。"""
    facts = {'httpVersion': response.http_version}
    headers = {}
    for name in ('content-type', 'content-encoding', 'content-length', 'transfer-encoding',
                 'connection', 'date', 'x-litellm-call-id', 'x-litellm-response-duration-ms',
                 'x-litellm-attempted-retries', 'x-litellm-attempted-fallbacks'):
        value = response.headers.get(name)
        if value and len(value) <= 200 and re.fullmatch(r'[A-Za-z0-9 .,:;/_+=()\-]+', value):
            headers[name] = value
    facts['responseHeaders'] = headers
    return facts
