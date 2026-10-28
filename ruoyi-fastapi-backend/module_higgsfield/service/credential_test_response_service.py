"""登记原始测试响应，不改变测试诊断与收费事实。"""
from module_higgsfield.dao.credential_test_dao import CredentialTestDao
from module_higgsfield.dao.credential_test_response_dao import CredentialTestResponseDao
from module_higgsfield.dao.provider_call_dao import ProviderCallDao
from module_higgsfield.entity.vo.provider_response_vo import ResponseFileFacts


class CredentialTestResponseService:
    @staticmethod
    async def register(db, test_id, call_id, facts, *, http_status):
        try:
            file = ResponseFileFacts.model_validate(facts)
            if type(http_status) is not int or not 100 <= http_status <= 599:
                raise ValueError('测试响应状态无效')
            test = await CredentialTestDao.locked(db, test_id)
            call = await ProviderCallDao.locked(db, call_id)
            if (test is None or call is None or test.provider_call_id != call_id
                    or call.operation != 'test' or call.cost_center_id != test.cost_center_id
                    or call.credential_version_id != test.credential_version_id
                    or call.request_metadata.get('testId') != str(test_id)
                    or call.request_metadata.get('configHash') != test.config_hash):
                raise ValueError('响应不属于当前测试调用')
            values = file.model_dump() | dict(test_id=test_id, provider_call_id=call_id, http_status=http_status)
            previous = await CredentialTestResponseDao.get(db, test_id)
            if previous is not None:
                if any(getattr(previous, key) != value for key, value in values.items()):
                    raise ValueError('测试响应证据不可覆盖')
                identity = previous.response_evidence_id
            else:
                if test.state != '0' or call.state != '1':
                    raise ValueError('测试响应已经终结，不能登记新证据')
                row = await CredentialTestResponseDao.add(db, values | dict(
                    create_by='credential-test-worker', update_by='credential-test-worker'))
                identity = row.response_evidence_id
            await db.commit()
            return identity
        except Exception:
            await db.rollback()
            raise
