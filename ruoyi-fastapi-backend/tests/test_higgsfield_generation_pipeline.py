"""真实准备链至预算受理集成验证；不调用外部供应商。"""

import base64
import importlib.util
import json
import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import text

from exceptions.exception import ServiceWarning
from module_higgsfield.entity.do.budget_do import HfBudget, HfBudgetPeriod
from module_higgsfield.entity.do.model_do import HfModelVariant
from module_higgsfield.entity.do.price_do import (
    HfPriceActivation,
    HfPriceBook,
    HfPriceRuleItem,
    HfPriceSource,
    HfPriceVersion,
    HfPriceVersionSource,
)
from module_higgsfield.entity.vo.generation_input_vo import GenerationInput
from module_higgsfield.entity.vo.generation_policy_vo import GenerationPolicy
from module_higgsfield.service.estimate_token_service import EstimateTokenService
from module_higgsfield.service.generation_accept_service import GenerationAcceptService
from module_higgsfield.service.generation_validation_service import GenerationValidationService
from module_higgsfield.service.write_service import WriteService
from tests import test_higgsfield_generation_route as route
from tests import test_higgsfield_job_storage as storage
from tests.test_higgsfield_model_capabilities import capability

MIGRATIONS = Path(__file__).resolve().parents[1] / 'alembic/versions'


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class GenerationPipelineTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = route.GenerationRouteTests.cleanup_schema
    job = route.GenerationRouteTests.job
    migrate = storage.JobStorageTests.migrate

    async def asyncSetUp(self) -> None:
        await route.GenerationRouteTests.asyncSetUp(self)
        for name in (
            '20261027_22_prices.py',
            '20261027_24_price_sources.py',
            '20261027_25_price_publish.py',
            '20261027_27_budgets.py',
        ):
            spec = importlib.util.spec_from_file_location('pipeline_setup', MIGRATIONS / name)
            self.migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.migration)
            await self.migrate('upgrade')
        self.owner.user.dept = None
        self.owner.user.dept_id = None
        self.policy = GenerationPolicy(platformCurrency='CNY', procurementCurrency='USD', missingBudgetPolicy='reject')
        self.secret = b'pipeline-test-estimate-signing-key'
        self.tokens = EstimateTokenService(self.secret)
        cap = capability().model_dump(by_alias=True)
        cap['referenceRules'] = {'maxTotal': 0, 'roles': {}}
        cap['estimatePolicy'] = {
            'strategy': 'fixed_usage_upper_bound',
            'evidenceRef': 'test-only/upper-bound',
            'scopeStatement': '仅集成测试固定上界',
            'upperBounds': {'videoTokens': '3000000'},
        }
        audit = WriteService.audit(self.owner)
        async with self.sessions() as db:
            await db.execute(
                text('UPDATE hf_model_profile_version SET capabilities=CAST(:cap AS jsonb)'), {'cap': json.dumps(cap)}
            )
            variant = HfModelVariant(
                model_version_id=int(self.model_version_id), variant_key='test', dimensions={}, **audit
            )
            source = HfPriceSource(
                source_type='manual_confirmation',
                excerpt='仅用于集成测试',
                observed_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
                create_user_id=self.owner.user.user_id,
                **audit,
            )
            db.add_all([variant, source])
            await db.flush()
            self.prices = {}
            for purpose, currency, account in (('platform', 'CNY', None), ('procurement', 'USD', int(self.account_id))):
                book = HfPriceBook(
                    model_variant_id=variant.variant_id,
                    purpose=purpose,
                    account_id=account,
                    currency=currency,
                    price_book_name=purpose,
                    **audit,
                )
                db.add(book)
                await db.flush()
                version = HfPriceVersion(
                    price_book_id=book.price_book_id,
                    version_no=1,
                    status='1',
                    rounding_mode='half_up',
                    calculation_scale=10,
                    create_user_id=self.owner.user.user_id,
                    **audit,
                )
                db.add(version)
                await db.flush()
                self.prices[purpose] = version.price_version_id
                db.add_all(
                    [
                        HfPriceRuleItem(
                            price_version_id=version.price_version_id,
                            item_code='video_tokens',
                            unit='token',
                            unit_quantity=1000000,
                            unit_price=2,
                            quantity_from=0,
                            formula_template='linear',
                            **audit,
                        ),
                        HfPriceVersionSource(
                            price_version_id=version.price_version_id, source_id=source.source_id, **audit
                        ),
                        HfPriceActivation(
                            price_book_id=book.price_book_id,
                            price_version_id=version.price_version_id,
                            effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
                            **audit,
                        ),
                    ]
                )
            budget = HfBudget(
                project_id=self.project_id,
                purpose='platform',
                currency='CNY',
                cycle_kind='total',
                business_timezone='Asia/Shanghai',
                **audit,
            )
            db.add(budget)
            await db.flush()
            db.add(
                HfBudgetPeriod(
                    budget_id=budget.budget_id,
                    period_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    limit_amount=10,
                    **audit,
                )
            )
            await db.commit()
        self.payload = GenerationInput(
            projectId=str(self.project_id),
            kind='image',
            modelVersionId=self.model_version_id,
            prompt={'content': []},
            parameters={'duration': 6},
            references=[],
        )

    async def test_preflight_to_real_acceptance_and_permanent_replay(self) -> None:
        async with self.sessions() as db:
            db.autoflush = False
            preview = await GenerationValidationService.validate(db, self.owner, self.payload, self.policy, self.tokens)
            self.assertTrue(preview['valid'], preview)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_creation_job')), 0)
            self.assertEqual(await db.scalar(text('SELECT reserved_amount FROM hf_budget_period')), 0)
            await db.rollback()
            submitted = self.payload.model_copy(update={'estimate_token': preview['estimateToken']})
            key = str(uuid4())
            with patch.dict(os.environ, {'HF_ESTIMATE_TOKEN_KEY': base64.b64encode(self.secret).decode()}):
                accepted, replayed = await GenerationAcceptService.accept(
                    db, self.owner, submitted, key, currencies=self.policy.currencies(), missing_budget_policy='reject'
                )
            self.assertFalse(replayed)
            row = (
                await db.execute(
                    text('SELECT credential_version_id,platform_price_version_id,input_snapshot FROM hf_creation_job')
                )
            ).one()
            self.assertEqual(row[0], self.key_id)
            self.assertEqual(row[1], self.prices['platform'])
            self.assertEqual(row[2]['estimate']['estimates']['platform']['total'], '6.0000000000')
            self.assertEqual(await db.scalar(text('SELECT reserved_amount FROM hf_budget_period')), 6)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_task_event')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_outbox_event')), 1)
            await db.execute(text("DELETE FROM hf_api_idempotency_record WHERE normalized_path='/generations'"))
            await db.commit()
            again, replayed = await GenerationAcceptService.accept(
                db, self.owner, submitted, key, currencies=self.policy.currencies(), missing_budget_policy='reject'
            )
            self.assertTrue(replayed)
            self.assertEqual(accepted['data'], again['data'])
            with self.assertRaises(ServiceWarning):
                await GenerationAcceptService.accept(
                    db,
                    self.owner,
                    submitted.model_copy(update={'parameters': {'duration': 8}}),
                    key,
                    currencies=self.policy.currencies(),
                    missing_budget_policy='reject',
                )

    async def test_price_change_after_preview_does_not_create_or_reserve(self) -> None:
        async with self.sessions() as db:
            db.autoflush = False
            preview = await GenerationValidationService.validate(db, self.owner, self.payload, self.policy, self.tokens)
            self.assertTrue(preview['valid'], preview)
            await db.execute(
                text(
                    "UPDATE hf_price_activation SET revision=revision+1,effective_until=clock_timestamp()+interval '1 day' WHERE price_version_id=:v"
                ),
                {'v': self.prices['platform']},
            )
            await db.commit()
            submitted = self.payload.model_copy(update={'estimate_token': preview['estimateToken']})
            with (
                patch.dict(os.environ, {'HF_ESTIMATE_TOKEN_KEY': base64.b64encode(self.secret).decode()}),
                self.assertRaises(ServiceWarning) as caught,
            ):
                await GenerationAcceptService.accept(
                    db,
                    self.owner,
                    submitted,
                    str(uuid4()),
                    currencies=self.policy.currencies(),
                    missing_budget_policy='reject',
                )
            self.assertEqual(caught.exception.data['errorCode'], 'PRICE_CHANGED')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_creation_job')), 0)
            self.assertEqual(await db.scalar(text('SELECT reserved_amount FROM hf_budget_period')), 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_task_event')), 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_budget_ledger_entry')), 0)
