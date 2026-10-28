from sqlalchemy import select, func
from module_higgsfield.entity.do.credential_test_do import HfCredentialTest
from module_higgsfield.entity.do.cost_center_do import HfCostCenter
from module_higgsfield.entity.do.provider_call_do import HfProviderCall


class CredentialTestDao:
    @staticmethod
    async def page(db, version_id, query):
        criteria = HfCredentialTest.credential_version_id == version_id
        total = await db.scalar(select(func.count()).select_from(HfCredentialTest).where(criteria))
        rows = list(await db.scalars(select(HfCredentialTest).where(criteria)
            .order_by(HfCredentialTest.test_id.desc()).offset((query.page_num - 1) * query.page_size)
            .limit(query.page_size)))
        return rows, total

    @staticmethod
    async def candidates(db, cutoff, limit):
        pending = list(await db.scalars(select(HfCredentialTest.test_id)
            .where(HfCredentialTest.state == '0', HfCredentialTest.provider_call_id.is_(None))
            .order_by(HfCredentialTest.update_time, HfCredentialTest.test_id).limit(limit)))
        stale = list(await db.scalars(select(HfCredentialTest.test_id)
            .join(HfProviderCall, HfProviderCall.call_id == HfCredentialTest.provider_call_id)
            .where(HfCredentialTest.state == '0', HfProviderCall.state == '1',
                   HfProviderCall.started_time <= cutoff)
            .order_by(HfCredentialTest.update_time, HfCredentialTest.test_id).limit(limit)))
        return pending, stale

    @staticmethod
    async def center(db, identity):
        return await db.scalar(select(HfCostCenter).where(HfCostCenter.cost_center_id == identity)
            .with_for_update().execution_options(populate_existing=True))

    @staticmethod
    async def add(db, values):
        row = HfCredentialTest(**values)
        db.add(row)
        await db.flush()
        return row

    @staticmethod
    async def get(db, identity):
        return await db.get(HfCredentialTest, identity)

    @staticmethod
    async def locked(db, identity):
        return await db.scalar(select(HfCredentialTest).where(HfCredentialTest.test_id == identity)
            .with_for_update().execution_options(populate_existing=True))
