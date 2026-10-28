"""按凭据供应商连接与区域筛选图片测试候选版本。"""
from sqlalchemy import select, func
from module_higgsfield.entity.do.model_do import HfModelProfile as Model, HfModelProfileVersion as Version


class CredentialTestModelDao:
    @staticmethod
    async def page(db, connection_id, region, query):
        statement = select(Version.model_version_id, Version.version_no, Version.gateway_alias,
            Version.status, Model.display_name).join(Model, Model.model_id == Version.model_id).where(
                Model.connection_id == connection_id, Model.kind == 'image', Version.region == region,
                Version.status != '3')
        total = await db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = (await db.execute(statement.order_by(Version.model_version_id.desc())
            .offset((query.page_num - 1) * query.page_size).limit(query.page_size))).all()
        return rows, total
