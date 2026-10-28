"""测试消费对象与不可变用量修订；与调用意图或完成事实共用事务。"""
from module_higgsfield.dao.usage_dao import UsageDao
from module_higgsfield.entity.do.usage_do import HfBillingSubject, HfUsageRecord
from module_higgsfield.service.usage_normalization_service import UsageNormalizationService
from module_higgsfield.entity.vo.usage_fact_vo import UsageFact


class CredentialTestUsageService:
    @staticmethod
    async def append(db, test, call, fact, *, now):
        """调用方已锁定测试；未知不是零，也不证明供应商未扣费。"""
        if (test.provider_call_id != call.call_id or call.operation != 'test' or call.job_id is not None
                or call.cost_center_id != test.cost_center_id or call.credential_version_id != test.credential_version_id
                or call.request_metadata.get('testId') != str(test.test_id)):
            raise ValueError('测试用量来源与成本中心归属不一致')
        fact = UsageFact.model_validate(fact.model_dump()) if fact is not None else UsageNormalizationService.image(None)
        if fact.parser_version != 'videoplus-image-usage-v1' or fact.source_path != 'choices[0].message.content.usage':
            raise ValueError('测试用量解析规则与当前图片探针不一致')
        audit = dict(create_by='credential-test-worker', update_by='credential-test-worker',
                     create_time=now, update_time=now)
        subject = await UsageDao.subject(db, call.call_id, 'test')
        if subject is None:
            subject = await UsageDao.add(db, HfBillingSubject, dict(account_id=call.account_id,
                cost_center_id=test.cost_center_id, origin_call_id=call.call_id, subject_kind='test',
                identity_key=f'test:{test.test_id}', **audit))
        if (subject.cost_center_id != test.cost_center_id or subject.job_id is not None
                or subject.account_id != call.account_id):
            raise ValueError('测试计费对象已存在不同归属')
        previous = await UsageDao.by_hash(db, subject.subject_id, fact.payload_hash)
        if previous is not None:
            return previous, False
        latest = await UsageDao.latest(db, subject.subject_id)
        row = await UsageDao.add(db, HfUsageRecord, fact.model_dump(exclude={'issues'}) | dict(
            subject_id=subject.subject_id, call_id=call.call_id,
            revision_no=latest.revision_no + 1 if latest else 1, **audit))
        return row, True
