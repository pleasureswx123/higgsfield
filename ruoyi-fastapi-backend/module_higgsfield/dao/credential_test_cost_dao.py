"""批量读取测试采购事件，不使用业务项目推断管理成本中心权限。"""
from sqlalchemy import select, func, and_
from module_higgsfield.entity.do.credential_test_do import HfCredentialTest as Test
from module_higgsfield.entity.do.provider_call_do import HfProviderCall as Call
from module_higgsfield.entity.do.usage_do import HfBillingSubject as Subject
from module_higgsfield.entity.do.billing_do import HfBillingEvent as Event, HfBillingAdjustment as Adjustment


class CredentialTestCostDao:
    @staticmethod
    async def for_tests(db, identities):
        if not identities:
            return []
        adjustments = select(func.coalesce(func.sum(Adjustment.delta_amount), 0)).where(
            Adjustment.event_id == Event.event_id).correlate(Event).scalar_subquery()
        return (await db.execute(select(Test.test_id, Call.call_id, Call.request_metadata,
            Event.event_id, Event.currency, Event.amount, Event.state, adjustments.label('adjustment_total'))
            .select_from(Test).outerjoin(Call, and_(Call.call_id == Test.provider_call_id,
                Call.credential_version_id == Test.credential_version_id, Call.cost_center_id == Test.cost_center_id,
                Call.operation == 'test'))
            .outerjoin(Subject, and_(Subject.origin_call_id == Call.call_id, Subject.subject_kind == 'test',
                Subject.cost_center_id == Test.cost_center_id, Subject.account_id == Call.account_id))
            .outerjoin(Event, and_(Event.subject_id == Subject.subject_id, Event.purpose == 'procurement'))
            .where(Test.test_id.in_(identities)))).mappings().all()
