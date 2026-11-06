"""验证诊断错误码、响应头白名单和秘密隔离，不连接供应商。"""
import unittest
import httpx
from module_higgsfield.service.provider_network_diagnostic import error_chain, response_facts


class NetworkDiagnosticTests(unittest.TestCase):
    def test_context_chain_keeps_os_codes_without_messages_and_handles_cycle(self):
        error = httpx.ReadError('Bearer secret https://private/path')
        inner = OSError(10054, 'secret')
        inner.winerror = 10054
        error.__context__ = inner
        inner.__context__ = error
        self.assertEqual(error_chain(error), [
            {'type':'ReadError'}, {'type':type(inner).__name__, 'errno':10054, 'winerror':10054}])
        self.assertNotIn('secret', str(error_chain(error)))

    def test_response_headers_exclude_secrets_budget_and_redirect_urls(self):
        response = httpx.Response(200, headers={
            'x-litellm-call-id':'safe-call-1', 'content-encoding':'br',
            'set-cookie':'secret', 'authorization':'secret', 'x-litellm-key-spend':'123',
            'location':'https://private/?token=secret'})
        self.assertEqual(response_facts(response)['responseHeaders'], {
            'content-encoding':'br', 'x-litellm-call-id':'safe-call-1'})
