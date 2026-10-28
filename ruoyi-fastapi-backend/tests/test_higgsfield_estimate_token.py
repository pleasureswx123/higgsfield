"""估价令牌篡改、跨作用域重放、到期与价格变化验证。"""

import base64
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from exceptions.exception import ServiceWarning
from module_higgsfield.entity.vo.generation_input_vo import GenerationInput
from module_higgsfield.service.estimate_token_service import EstimateTokenService


class EstimateTokenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = EstimateTokenService(b'test-only-estimate-key-32-bytes!!!')
        self.now = datetime(2026, 10, 27, tzinfo=timezone.utc)
        self.payload = GenerationInput(
            projectId='1', kind='image', modelVersionId='2', prompt={'content': []}, parameters={}, references=[]
        )
        self.prices = {
            'platform': {'priceVersionId': '1', 'selectedAt': 'old'},
            'procurement': {'priceVersionId': '2', 'unitPrice': 'secret-price'},
        }
        self.estimate = {'inputHash': 'fixed', 'policy': {'schemaVersion': 1}}
        self.arguments = {
            'actor_id': 3,
            'payload': self.payload,
            'prices': self.prices,
            'estimate': self.estimate,
            'now': self.now,
        }
        self.token = self.service.issue(**self.arguments)

    def test_same_quote_read_time_and_token_field_do_not_change_binding(self) -> None:
        prices = {**self.prices, 'platform': {'priceVersionId': '1', 'selectedAt': 'new'}}
        payload = self.payload.model_copy(update={'estimate_token': self.token})
        self.service.verify(self.token, **(self.arguments | {'prices': prices, 'payload': payload}))
        body = self.token.split('.')[0]
        claims = json.loads(base64.urlsafe_b64decode(body + '=' * (-len(body) % 4)))
        self.assertNotIn('secret-price', str(claims))

    def test_tampering_scope_expiry_and_price_changes(self) -> None:
        for token, changes, code in (
            (self.token + 'x', {}, 'ESTIMATE_TOKEN_INVALID'),
            (self.token, {'actor_id': 4}, 'ESTIMATE_TOKEN_INVALID'),
            (self.token, {'payload': self.payload.model_copy(update={'project_id': '4'})}, 'ESTIMATE_TOKEN_INVALID'),
            (
                self.token,
                {'payload': self.payload.model_copy(update={'parameters': {'n': 2}})},
                'ESTIMATE_TOKEN_INVALID',
            ),
            (self.token, {'now': self.now + timedelta(seconds=300)}, 'ESTIMATE_EXPIRED'),
            (self.token, {'now': self.now - timedelta(seconds=1)}, 'ESTIMATE_TOKEN_INVALID'),
            (self.token, {'prices': {}}, 'PRICE_CHANGED'),
            (self.token, {'estimate': {'policy': {'schemaVersion': 2}}}, 'PRICE_CHANGED'),
        ):
            with self.subTest(code=code), self.assertRaises(ServiceWarning) as caught:
                self.service.verify(token, **(self.arguments | changes))
            self.assertEqual(caught.exception.data['errorCode'], code)

    def test_no_default_secret_or_unbounded_ttl(self) -> None:
        with patch.dict('os.environ', {}, clear=True), self.assertRaises(ValueError):
            EstimateTokenService.from_environment()
        with self.assertRaises(ValueError):
            EstimateTokenService(b'short')
        with self.assertRaises(ValueError):
            self.service.issue(**self.arguments, ttl_seconds=3601)
