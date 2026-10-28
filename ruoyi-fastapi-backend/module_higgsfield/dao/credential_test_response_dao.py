"""测试响应索引只新增及读取，不提供覆盖与删除。"""
from sqlalchemy import select
from module_higgsfield.entity.do.credential_test_response_do import HfCredentialTestResponse


class CredentialTestResponseDao:
    @staticmethod
    async def get(db, test_id):
        return await db.scalar(select(HfCredentialTestResponse).where(HfCredentialTestResponse.test_id == test_id))

    @staticmethod
    async def add(db, values):
        row = HfCredentialTestResponse(**values)
        db.add(row)
        await db.flush()
        return row
