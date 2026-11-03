"""修复解析兼容性后复核已保存响应，不重新发送或重复登记消费。"""
import asyncio

from module_higgsfield.dao.credential_test_dao import CredentialTestDao
from module_higgsfield.dao.credential_test_response_dao import CredentialTestResponseDao
from module_higgsfield.dao.provider_call_dao import ProviderCallDao
from module_higgsfield.dao.job_lease_dao import JobLeaseDao
from module_higgsfield.dao.price_source_dao import PriceSourceDao
from module_higgsfield.service.credential_test_image_probe_service import CredentialTestImageProbeService
from module_higgsfield.service.provider_http_service import ProviderHttpResult


class CredentialTestRecheckService:
    @staticmethod
    def eligible(test, call, evidence):
        return (
            test is not None and test.state == '2' and test.model_version_id is not None
            and isinstance(test.result, dict) and test.result.get('issue') == 'RESPONSE_INVALID'
            and test.result.get('transport') == 'response'
            and call is not None and call.call_id == test.provider_call_id
            and call.state == '2' and call.operation == 'test' and call.job_id is None
            and call.credential_version_id == test.credential_version_id
            and call.cost_center_id == test.cost_center_id and call.actor_id == test.requested_by
            and call.request_metadata.get('testId') == str(test.test_id)
            and call.request_metadata.get('configHash') == test.config_hash
            and call.response_metadata == test.result
            and evidence is not None and evidence.provider_call_id == call.call_id
            and evidence.http_status == call.http_status == test.result.get('httpStatus')
        )

    @classmethod
    async def recheck(cls, sessions, storage, evidence_storage, *, test_id, max_bytes, apply=False):
        """默认只读；写入仅更新核验结论，保留原诊断审计及原响应、账目。"""
        async with sessions() as db:
            test = await CredentialTestDao.locked(db, test_id)
            call = await ProviderCallDao.locked(db, test.provider_call_id) if test else None
            evidence = await CredentialTestResponseDao.get(db, test_id)
            if not cls.eligible(test, call, evidence):
                raise ValueError('仅允许复核保留完整响应的解析失败测试')
            call_id, before = call.call_id, dict(test.result)
            facts = {key: getattr(evidence, key) for key in ('storage_key', 'sha256', 'byte_size')}
            http_status = evidence.http_status
        body = await evidence_storage.load(facts, call_id, test_id)
        result = await asyncio.to_thread(CredentialTestImageProbeService.parse,
            ProviderHttpResult(transport='response', http_status=http_status, body=body),
            max_bytes=max_bytes, verify_media=storage.verify_media)
        after = result.diagnostic.model_dump(by_alias=True)
        if not apply or not result.diagnostic.model_verified:
            return after
        async with sessions() as db:
            try:
                test = await CredentialTestDao.locked(db, test_id)
                call = await ProviderCallDao.locked(db, call_id)
                evidence = await CredentialTestResponseDao.get(db, test_id)
                if (not cls.eligible(test, call, evidence) or test.result != before
                        or any(getattr(evidence, key) != value for key, value in facts.items())):
                    raise ValueError('复核期间测试或响应证据发生变化')
                now = await JobLeaseDao.now(db)
                actor = 'credential-response-recheck'
                await PriceSourceDao.audit(db, dict(actor_kind='system', object_type='credential_test',
                    object_id=str(test_id), action='recheck_saved_response',
                    request_id=f'credential-response-recheck-{test_id}-{facts["sha256"][:32]}',
                    reason='修复网关空格式、空尺寸兼容后，校验原响应摘要、解密并实际解码图片；未重发供应商请求',
                    before_after={'before': before, 'after': after, 'responseSha256': facts['sha256'],
                                  'providerCallId': str(call_id)},
                    create_by=actor, update_by=actor, create_time=now, update_time=now))
                test.state, test.result = '1', after
                call.acceptance, call.response_metadata = result.diagnostic.acceptance, after
                test.update_by = call.update_by = actor
                test.update_time = call.update_time = now
                await db.commit()
            except Exception:
                await db.rollback()
                raise
        return after
