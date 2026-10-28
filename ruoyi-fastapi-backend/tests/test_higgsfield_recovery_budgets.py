"""恢复预算核验验证十位小数守恒、超额事实和只读行为。"""

import importlib.util
import copy
import json
import os
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from types import SimpleNamespace
from pathlib import Path
import unittest
from sqlalchemy import text
from module_higgsfield.service.recovery_budget_service import RecoveryBudgetService
from module_higgsfield.service.exchange_rate_service import ExchangeRateService
from tests import test_higgsfield_output_read as reads


class RecoveryConversionTests(unittest.TestCase):
    def test_historical_direction_rounding_and_adjustment(self):
        at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        rate = dict(exchange_rate_id=7, base_currency='USD', quote_currency='CNY',
                    rate=Decimal('3'), valid_from=at, valid_until=at + timedelta(days=1), status='1')
        snapshot = ExchangeRateService.convert(SimpleNamespace(**rate), '1', 'CNY', 'USD', at=at, scale=10)
        row = dict(**rate, exchange_rate_version_id=7, budget_currency='USD', entry_type='settle',
                   conversion_snapshot=snapshot, consumed_delta=Decimal('0.3333333333'), reserved_delta=Decimal(0))
        self.assertTrue(RecoveryBudgetService.conversion_valid(row))
        for key, value in (('direction', 'multiply'), ('rate', '4'), ('rawAmount', '0.3'),
                           ('amount', '0.3333333334'), ('roundingMode', 'ceiling'),
                           ('calculationScale', True), ('exchangeRateVersionId', '8'),
                           ('at', '2026-01-02T00:00:00+00:00'), ('at', '2026-01-01T00:00:00'),
                           ('sourceAmount', 'NaN'), ('targetCurrency', 'CNY')):
            broken = copy.deepcopy(row)
            broken['conversion_snapshot'][key] = value
            with self.subTest(key=key, value=value):
                self.assertFalse(RecoveryBudgetService.conversion_valid(broken))
        for invalid in (None, [], {}, 'private'):
            self.assertFalse(RecoveryBudgetService.conversion_valid({**row, 'conversion_snapshot': invalid}))
        reserved = copy.deepcopy(row)
        reserved.update(entry_type='reserve', reserved_delta=Decimal('0.3333333334'))
        reserved['conversion_snapshot'].update(amount='0.3333333334', roundingMode='ceiling')
        self.assertTrue(RecoveryBudgetService.conversion_valid(reserved))
        # 累计两单位兑换后减一单位的舍入结果，差额比单次兑换多一个最小单位。
        adjusted = copy.deepcopy(row)
        adjusted.update(entry_type='adjust', consumed_delta=Decimal('0.3333333334'))
        adjusted['conversion_snapshot'] = ExchangeRateService.convert(
            SimpleNamespace(**rate), '2', 'CNY', 'USD', at=at, scale=10)
        adjusted['conversion_snapshot'].update(previousConvertedAmount='0.3333333333',
            convertedDelta='0.3333333334', sourceAdjustmentAmount='1')
        self.assertTrue(RecoveryBudgetService.conversion_valid(adjusted))
        adjusted['conversion_snapshot']['previousConvertedAmount'] = '0.3333333334'
        self.assertFalse(RecoveryBudgetService.conversion_valid(adjusted))
        adjusted['conversion_snapshot'] = {**snapshot, 'previousConvertedAmount': '0.6666666667',
            'convertedDelta': '-0.3333333334', 'sourceAdjustmentAmount': '-1'}
        adjusted['consumed_delta'] = Decimal('-0.3333333334')
        self.assertTrue(RecoveryBudgetService.conversion_valid(adjusted))
        self.assertFalse(RecoveryBudgetService.conversion_valid({**row, 'status': '0'}))
        self.assertFalse(RecoveryBudgetService.conversion_valid({**row, 'exchange_rate_id': None}))


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class RecoveryBudgetTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = reads.OutputReadTests.cleanup_schema
    migrate = reads.OutputReadTests.migrate
    job = reads.OutputReadTests.job
    output = reads.OutputReadTests.output
    create = reads.OutputReadTests.create

    async def asyncSetUp(self):
        await reads.OutputReadTests.asyncSetUp(self)
        for filename in ('20261027_27_budgets.py', '20261027_26_exchange_rates.py', '20261027_39_billing_facts.py'):
            spec = importlib.util.spec_from_file_location('recovery_budget',
                Path(__file__).resolve().parents[1] / 'alembic/versions' / filename)
            self.migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.migration)
            await self.migrate('upgrade')

    async def test_exact_deltas_reservations_and_cache_are_not_rewritten(self):
        async with self.sessions() as db:
            await db.execute(text(
                "INSERT INTO hf_billing_event(subject_id,purpose,price_version_id,currency,amount,state,create_time,update_time) "
                "VALUES(1,'platform',1,'CNY',1,'2',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
            budget = await db.scalar(text(
                "INSERT INTO hf_budget(project_id,purpose,currency,cycle_kind,business_timezone,create_time,update_time) "
                "VALUES(1,'platform','CNY','total','Asia/Shanghai',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP) RETURNING budget_id"))
            period = await db.scalar(text(
                'INSERT INTO hf_budget_period(budget_id,period_start,limit_amount,reserved_amount,consumed_amount,create_time,update_time) '
                'VALUES(:budget,CURRENT_TIMESTAMP,1,3.0000000001,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP) RETURNING period_id'
            ), {'budget': budget})
            reservation = await db.scalar(text(
                "INSERT INTO hf_budget_reservation(job_id,period_id,original_amount,remaining_amount,state,create_time,update_time) "
                "VALUES(1,:period,4.0000000001,3.0000000001,'4',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP) RETURNING reservation_id"
            ), {'period': period})
            for kind, reserved, consumed, limit in (
                ('change_limit', '0', '0', '1'), ('reserve', '4.0000000001', '0', '0'), ('settle', '-1', '1', '0'),
            ):
                await db.execute(text(
                    'INSERT INTO hf_budget_ledger_entry(period_id,reservation_id,billing_event_id,business_event_key,entry_type,'
                    'reserved_delta,consumed_delta,limit_delta,reason,create_time,update_time) '
                    "VALUES(:period,:reservation,1,:kind,:kind,CAST(:reserved AS numeric),CAST(:consumed AS numeric),CAST(:limit AS numeric),'测试',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                ), dict(period=period, reservation=reservation, kind=kind, reserved=reserved, consumed=consumed, limit=limit))
            await db.commit()
        # 允许超额；待确认状态的剩余预占仍必须计入，不能按状态静默排除。
        self.assertEqual((await RecoveryBudgetService.audit(self.sessions, page_size=1))['failed'], 0)
        async with self.sessions() as db:
            rate_id = await db.scalar(text(
                "INSERT INTO hf_exchange_rate_version(base_currency,quote_currency,rate,valid_from,source_id,status,create_time,update_time) "
                "VALUES('USD','CNY',1,'2026-01-01T00:00:00Z',1,'1',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP) RETURNING exchange_rate_id"))
            snapshot = ExchangeRateService.convert(SimpleNamespace(exchange_rate_id=rate_id,
                base_currency='USD', quote_currency='CNY', rate=Decimal(1), status='1',
                valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc), valid_until=None),
                '4.0000000001', 'USD', 'CNY', at=datetime(2026, 1, 2, tzinfo=timezone.utc), scale=10)
            snapshot['roundingMode'] = 'ceiling'
            await db.execute(text("UPDATE hf_budget_ledger_entry SET exchange_rate_version_id=:rate,conversion_snapshot=CAST(:snapshot AS jsonb) WHERE entry_type='reserve'"),
                             {'rate': rate_id, 'snapshot': json.dumps(snapshot)})
            await db.commit()
        self.assertEqual((await RecoveryBudgetService.audit(self.sessions, page_size=1))['failed'], 0)
        async with self.sessions() as db:
            await db.execute(text("UPDATE hf_budget_ledger_entry SET conversion_snapshot=jsonb_set(conversion_snapshot,'{direction}','\"divide\"') WHERE entry_type='reserve'"))
            await db.commit()
        report = await RecoveryBudgetService.audit(self.sessions, page_size=1, sample_limit=0)
        self.assertEqual(report['failed'], 1, report)
        self.assertEqual(report['counts']['ledger_conversion_invalid'], 1)
        self.assertEqual(report['failures'], [])
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text("SELECT conversion_snapshot->>'direction' FROM hf_budget_ledger_entry WHERE entry_type='reserve'")), 'divide')
            await db.execute(text("UPDATE hf_budget_ledger_entry SET exchange_rate_version_id=NULL,conversion_snapshot='{}' WHERE entry_type='reserve'"))
            await db.commit()
        async with self.sessions() as db:
            await db.execute(text('UPDATE hf_budget_period SET limit_amount=1.0000000001,reserved_amount=3.0000000002,consumed_amount=1.0000000001'))
            await db.commit()
        report = await RecoveryBudgetService.audit(self.sessions, page_size=1, sample_limit=1)
        self.assertEqual(report['failed'], 4)
        self.assertTrue(all(report['counts'][rule] == 1 for rule in (
            'limit_ledger_mismatch', 'reserved_ledger_mismatch', 'consumed_ledger_mismatch', 'reservation_balance_mismatch')))
        self.assertEqual(len(report['failures']), 1)
        self.assertTrue(report['failuresTruncated'])
        self.assertEqual(report['failures'][0]['periodId'], str(period))
        async with self.sessions() as db:
            self.assertEqual(str(await db.scalar(text('SELECT reserved_amount FROM hf_budget_period'))), '3.0000000002')
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_budget_ledger_entry')), 3)
            await db.execute(text('UPDATE hf_budget_period SET limit_amount=1,reserved_amount=3.0000000001,consumed_amount=1'))
            await db.execute(text('UPDATE hf_budget_reservation SET remaining_amount=3'))
            await db.commit()
        report = await RecoveryBudgetService.audit(self.sessions, sample_limit=0)
        self.assertEqual(report['failed'], 2)
        self.assertEqual(report['counts']['reservation_balance_mismatch'], 1)
        self.assertEqual(report['counts']['reservation_ledger_mismatch'], 1)
        self.assertEqual(report['failures'], [])

    async def test_orphan_records_are_found_outside_period_pagination(self):
        async with self.sessions() as db:
            period = await db.scalar(text(
                'INSERT INTO hf_budget_period(budget_id,period_start,limit_amount,create_time,update_time) '
                'VALUES(999999,CURRENT_TIMESTAMP,0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP) RETURNING period_id'
            ))
            reservation = await db.scalar(text(
                'INSERT INTO hf_budget_reservation(job_id,period_id,original_amount,remaining_amount,create_time,update_time) '
                'VALUES(999999,999999,1,0.5,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP) RETURNING reservation_id'
            ))
            for key, owner_period, owner_reservation, delta, kind in (
                ('orphan-period', 999999, reservation, '1', 'reserve'),
                ('missing-reservation', 999999, 888888, '1', 'reserve'),
                ('cross-period', period, reservation, '-0.1', 'release'),
            ):
                await db.execute(text(
                    'INSERT INTO hf_budget_ledger_entry(period_id,reservation_id,business_event_key,entry_type,'
                    'reserved_delta,consumed_delta,limit_delta,reason,create_time,update_time) '
                    "VALUES(:period,:reservation,:key,:kind,CAST(:delta AS numeric),0,0,'恢复故障夹具',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                ), dict(period=owner_period, reservation=owner_reservation, key=key, kind=kind, delta=delta))
            await db.commit()
        report = await RecoveryBudgetService.audit(self.sessions, page_size=1)
        expected = ('period_budget_missing', 'reservation_period_missing', 'reservation_job_missing',
                    'ledger_period_missing', 'ledger_reservation_missing',
                    'ledger_reservation_period_mismatch', 'reservation_ledger_mismatch')
        self.assertTrue(all(report['counts'][rule] > 0 for rule in expected), report)
        self.assertEqual(report['counts']['ledger_period_missing'], 2)
        self.assertNotIn('恢复故障夹具', str(report))
        limited = await RecoveryBudgetService.audit(self.sessions, sample_limit=0)
        self.assertEqual(limited['counts'], report['counts'])
        self.assertEqual(limited['failures'], [])
        self.assertTrue(limited['failuresTruncated'])
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_budget_ledger_entry WHERE period_id=999999')), 2)
            self.assertEqual(await db.scalar(text('SELECT period_id FROM hf_budget_reservation')), 999999)

    async def test_billing_evidence_and_purpose_are_not_inferred_from_equal_totals(self):
        async with self.sessions() as db:
            budget = await db.scalar(text(
                "INSERT INTO hf_budget(project_id,purpose,currency,cycle_kind,business_timezone,create_time,update_time) "
                "VALUES(1,'platform','CNY','total','Asia/Shanghai',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP) RETURNING budget_id"))
            period = await db.scalar(text(
                'INSERT INTO hf_budget_period(budget_id,period_start,limit_amount,consumed_amount,create_time,update_time) '
                'VALUES(:budget,CURRENT_TIMESTAMP,0,2,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP) RETURNING period_id'
            ), {'budget': budget})
            events = []
            for subject, purpose in ((1, 'procurement'), (2, 'platform')):
                events.append(await db.scalar(text(
                    'INSERT INTO hf_billing_event(subject_id,purpose,price_version_id,currency,amount,state,create_time,update_time) '
                    "VALUES(:subject,:purpose,1,'CNY',1,'2',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP) RETURNING event_id"
                ), {'subject': subject, 'purpose': purpose}))
            adjustment = await db.scalar(text(
                'INSERT INTO hf_billing_adjustment(event_id,adjustment_key,delta_amount,reason,create_time,update_time) '
                "VALUES(:event,'restore-adjustment',1,'测试',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP) RETURNING adjustment_id"
            ), {'event': events[1]})
            for key, event, adjustment_id, exchange in (
                ('missing-evidence', 999999, 999999, 999999),
                ('wrong-owner', events[0], adjustment, None),
            ):
                await db.execute(text(
                    'INSERT INTO hf_budget_ledger_entry(period_id,billing_event_id,adjustment_id,exchange_rate_version_id,'
                    'business_event_key,entry_type,reserved_delta,consumed_delta,limit_delta,reason,create_time,update_time) '
                    "VALUES(:period,:event,:adjustment,:exchange,:key,'adjust',0,1,0,'测试',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                ), dict(period=period, event=event, adjustment=adjustment_id, exchange=exchange, key=key))
            await db.commit()
        report = await RecoveryBudgetService.audit(self.sessions)
        expected = ('ledger_billing_event_missing', 'ledger_adjustment_missing',
                    'ledger_adjustment_event_mismatch', 'ledger_exchange_rate_missing',
                    'ledger_billing_purpose_mismatch')
        self.assertEqual(report['failed'], 6, report)
        self.assertEqual(report['counts']['ledger_conversion_invalid'], 1)
        self.assertTrue(all(report['counts'][rule] == 1 for rule in expected))
        self.assertEqual(report['counts']['consumed_ledger_mismatch'], 0)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(text('SELECT count(*) FROM hf_budget_ledger_entry')), 2)
            self.assertEqual(await db.scalar(text('SELECT event_id FROM hf_billing_adjustment')), events[1])
