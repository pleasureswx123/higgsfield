"""受理事务使用受控准备结果，验证真实任务、预算及消息原子性。"""

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from sqlalchemy import text

from exceptions.exception import ServiceWarning
from module_higgsfield.dao.job_event_dao import JobEventDao
from module_higgsfield.entity.vo.generation_input_vo import GenerationInput
from module_higgsfield.entity.vo.generation_policy_vo import GenerationPolicy
from module_higgsfield.service.estimate_token_service import EstimateTokenService
from module_higgsfield.service.generation_accept_service import GenerationAcceptService
from module_higgsfield.service.generation_preparation_service import GenerationPreparationService
from module_higgsfield.service.generation_validation_service import GenerationValidationService
from tests import test_higgsfield_generation_cancel as cancel


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class GenerationAcceptTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = cancel.GenerationCancelTests.cleanup_schema
    migrate = cancel.GenerationCancelTests.migrate
    job = cancel.GenerationCancelTests.job
    output = cancel.GenerationCancelTests.output
    create = cancel.GenerationCancelTests.create

    async def asyncSetUp(self) -> None:
        await cancel.GenerationCancelTests.asyncSetUp(self)
        self.owner.user.dept = None
        self.owner.user.dept_id = None
        async with self.sessions() as db:
            self.project_id = await db.scalar(text('SELECT project_id FROM hf_creation_job LIMIT 1'))
            await db.execute(
                text(
                    "INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope,create_time,update_time) SELECT role_id,'generation:create','project',NOW(),NOW() FROM hf_project_role WHERE code='owner' ON CONFLICT DO NOTHING"
                )
            )
            await db.execute(
                text(
                    "INSERT INTO hf_budget(project_id,purpose,currency,cycle_kind,business_timezone,create_time,update_time) VALUES(:p,'platform','CNY','total','Asia/Shanghai',NOW(),NOW())"
                ),
                {'p': self.project_id},
            )
            await db.commit()
        self.payload = GenerationInput(
            projectId=str(self.project_id),
            kind='image',
            modelVersionId='1',
            prompt={'content': []},
            parameters={},
            references=[],
        )
        self.prepared = {
            'modelVersionId': '1',
            'modelVariantId': '1',
            'acceptedAt': datetime.now(timezone.utc),
            'route': {'credentialVersionId': '1'},
            'prices': {'platform': {'priceVersionId': '1'}, 'procurement': {'priceVersionId': '2'}},
            'estimate': {
                'estimates': {
                    'platform': {'currency': 'CNY', 'total': '20'},
                    'procurement': {'currency': 'USD', 'total': '5'},
                }
            },
            'inputSnapshot': {
                'prompt': {'content': []},
                'parameters': {},
                'references': [],
                'compiled': {'media': [], 'sources': []},
            },
        }

    async def accept(self, key: str) -> tuple:
        async with self.sessions() as db:
            db.autoflush = False
            with patch.object(GenerationPreparationService, 'prepare', AsyncMock(return_value=self.prepared)):
                return await GenerationAcceptService.accept(
                    db,
                    self.owner,
                    self.payload,
                    key,
                    currencies={'platform': 'CNY', 'procurement': 'USD'},
                    missing_budget_policy='reject',
                )

    async def test_permanent_replay_and_single_reservation(self) -> None:
        key = str(uuid4())
        first = await self.accept(key)
        again = await self.accept(key)
        self.assertTrue(again[1])
        self.assertEqual(first[0]['data'], again[0]['data'])
        async with self.sessions() as db:
            snapshot = await db.scalar(text('SELECT input_snapshot FROM hf_creation_job WHERE job_id=:id'),
                {'id': int(first[0]['data']['id'])})
            self.assertEqual(snapshot['budgetReservations'][0]['originalAmount'], '20.0000000000')
            self.assertEqual(snapshot['budgetReservations'][0]['conversion'], {})
            await db.execute(text("DELETE FROM hf_api_idempotency_record WHERE normalized_path='/generations'"))
            await db.commit()
        replay = await self.accept(key)
        self.assertEqual(first[0]['data'], replay[0]['data'])
        async with self.sessions() as db:
            self.assertEqual(
                await db.scalar(text('SELECT reserved_amount FROM hf_budget_period WHERE period_id=1')), 80
            )
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_task_event')), 1)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_outbox_event')), 1)

    async def test_target_snapshot_persists_and_key_cannot_change_target(self) -> None:
        self.payload = self.payload.model_copy(update={'target_element_id': '9007199254740993'})
        self.prepared['inputSnapshot']['targetElementId'] = '9007199254740993'
        key = str(uuid4())
        first = await self.accept(key)
        async with self.sessions() as db:
            snapshot = await db.scalar(text('SELECT input_snapshot FROM hf_creation_job WHERE job_id=:id'),
                {'id': int(first[0]['data']['id'])})
            self.assertEqual(snapshot['targetElementId'], '9007199254740993')
            self.assertNotIn('targetElementId', snapshot['compiled'])
        self.payload = self.payload.model_copy(update={'target_element_id': '2'})
        with self.assertRaises(ServiceWarning):
            await self.accept(key)

    async def test_insufficient_budget_and_event_failure_rollback(self) -> None:
        self.prepared['estimate']['estimates']['platform']['total'] = '41'
        with self.assertRaises(ServiceWarning):
            await self.accept(str(uuid4()))
        self.prepared['estimate']['estimates']['platform']['total'] = '20'
        with (
            patch.object(JobEventDao, 'state', AsyncMock(side_effect=RuntimeError('事件故障'))),
            self.assertRaises(RuntimeError),
        ):
            await self.accept(str(uuid4()))
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_creation_job')), 1)
            self.assertEqual(
                await db.scalar(text('SELECT reserved_amount FROM hf_budget_period WHERE period_id=1')), 60
            )
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_budget_ledger_entry')), 0)
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_task_event')), 0)

    async def test_preflight_does_not_reserve_and_hides_prices(self) -> None:
        policy = GenerationPolicy(platformCurrency='CNY', procurementCurrency='USD', missingBudgetPolicy='reject')
        tokens = EstimateTokenService(b'test-only-estimate-key-32-bytes!!!')
        async with self.sessions() as db:
            with patch.object(GenerationPreparationService, 'prepare', AsyncMock(return_value=self.prepared)):
                result = await GenerationValidationService.validate(db, self.owner, self.payload, policy, tokens)
            self.assertTrue(result['valid'])
            self.assertEqual(result['estimateVisibility'], 'hidden')
            self.assertNotIn('estimate', result)
            self.assertNotIn('priceVersionId', result)
            self.assertFalse(db.in_transaction())

            self.assertEqual(
                await db.scalar(text('SELECT reserved_amount FROM hf_budget_period WHERE period_id=1')), 60
            )
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_creation_job')), 1)
            await db.rollback()
            self.prepared['estimate']['estimates']['platform']['total'] = '41'
            with patch.object(GenerationPreparationService, 'prepare', AsyncMock(return_value=self.prepared)):
                rejected = await GenerationValidationService.validate(db, self.owner, self.payload, policy, tokens)
            self.assertFalse(rejected['valid'])
            self.assertEqual(rejected['issues'][0]['code'], 'BUDGET_INSUFFICIENT')
            self.assertNotIn('estimateToken', rejected)
            self.assertFalse(db.in_transaction())

    async def test_preflight_platform_estimate_requires_both_permission_scopes(self):
        policy = GenerationPolicy(platformCurrency='CNY', procurementCurrency='USD', missingBudgetPolicy='reject')
        tokens = EstimateTokenService(b'test-only-estimate-key-32-bytes!!!')
        self.prepared['estimate']['estimates']['platform']['priceVersionId'] = '1'
        async with self.sessions() as db:
            await db.execute(
                text(
                    "INSERT INTO hf_project_role_permission(role_id,permission_code,data_scope) SELECT role_id,'project:usage:read','project' FROM hf_project_role WHERE code='owner' ON CONFLICT DO NOTHING"
                )
            )
            await db.commit()
            with patch.object(GenerationPreparationService, 'prepare', AsyncMock(return_value=self.prepared)):
                visible = await GenerationValidationService.validate(db, self.owner, self.payload, policy, tokens)
            self.assertEqual(visible['estimateVisibility'], 'visible')
            self.assertEqual(visible['estimate'], {'amount': '20', 'currency': 'CNY'})
            self.assertNotIn('procurement', str(visible))
            self.owner.permissions = ['generation:create', 'billing:read']
            with patch.object(GenerationPreparationService, 'prepare', AsyncMock(return_value=self.prepared)):
                hidden = await GenerationValidationService.validate(db, self.owner, self.payload, policy, tokens)
            self.assertEqual(hidden['estimateVisibility'], 'hidden')
            self.assertNotIn('estimate', hidden)
            self.owner.permissions = ['generation:create', 'project:usage:read']
            await db.execute(text("DELETE FROM hf_project_role_permission WHERE permission_code='project:usage:read'"))
            await db.commit()
            with patch.object(GenerationPreparationService, 'prepare', AsyncMock(return_value=self.prepared)):
                revoked = await GenerationValidationService.validate(db, self.owner, self.payload, policy, tokens)
            self.assertEqual(revoked['estimateVisibility'], 'hidden')
            self.assertNotIn('estimate', revoked)
