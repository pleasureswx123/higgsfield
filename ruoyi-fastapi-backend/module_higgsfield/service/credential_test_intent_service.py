"""先提交测试调用意图，后发送；已有意图的测试绝不自动重发。"""
from dataclasses import dataclass
from module_higgsfield.dao.credential_test_dao import CredentialTestDao
from module_higgsfield.dao.job_lease_dao import JobLeaseDao
from module_higgsfield.dao.provider_call_dao import ProviderCallDao
from module_higgsfield.service.credential_test_binding_service import CredentialTestBindingService, CredentialTestBinding
from module_higgsfield.service.write_service import WriteService
from module_higgsfield.service.credential_test_usage_service import CredentialTestUsageService
from module_higgsfield.service.credential_test_price_service import CredentialTestPriceService


@dataclass(repr=False)
class CredentialTestIntent:
    call_id: int
    binding: CredentialTestBinding
    payload: dict


class CredentialTestIntentService:
    @staticmethod
    async def begin(db, test_id, compile_probe, *, procurement_currency=None):
        """执行器内部入口；同步编译器只能构造请求，禁止网络和存储副作用。

        返回空值表示该测试已被领取或终结。调用方仅可发送本次返回的意图，
        不得从已有调用记录恢复发送。提交后进程中断须进入未知结果处理。
        """
        try:
            row = await CredentialTestDao.locked(db, test_id)
            if row is None or row.state != '0' or row.provider_call_id is not None:
                await db.commit()
                return None
            binding = await CredentialTestBindingService.require(db, row.credential_version_id,
                row.cost_center_id, row.model_version_id, expected_hash=row.config_hash)
            payload = compile_probe(binding)
            if not isinstance(payload, dict) or not payload:
                raise ValueError('测试编译器必须返回非空请求对象')
            now = await JobLeaseDao.now(db)
            pricing = await CredentialTestPriceService.freeze(db, binding, payload,
                currency=procurement_currency, at=now)
            call = await ProviderCallDao.add(db, dict(cost_center_id=row.cost_center_id,
                account_id=binding.account.account_id, credential_version_id=row.credential_version_id,
                operation='test', request_hash=WriteService.digest(payload),
                request_metadata={'testId': str(row.test_id), 'configHash': row.config_hash,
                                  'connectionVersionId': str(row.connection_version_id), 'procurementPricing': pricing},
                state='1', acceptance='unknown', actor_id=row.requested_by, started_time=now,
                create_by=str(row.requested_by), update_by=str(row.requested_by)))
            row.provider_call_id = call.call_id
            row.update_by = str(row.requested_by)
            row.update_time = now
            await CredentialTestUsageService.append(db, row, call, None, now=now)
            intent = CredentialTestIntent(call.call_id, binding, payload)
            await db.commit()
            return intent
        except Exception:
            await db.rollback()
            raise
