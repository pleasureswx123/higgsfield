"""价格簿属于全局模型元数据，仅全管理范围的费用角色可操作。"""

from common.vo import PageModel
from module_higgsfield.dao.price_dao import PriceDao
from module_higgsfield.service.admin_scope_service import AdminScopeService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService


class PriceService:
    @staticmethod
    def book(row):
        return {
            'id': str(row.price_book_id),
            'modelVariantId': str(row.model_variant_id),
            'purpose': row.purpose,
            'accountId': str(row.account_id) if row.account_id else None,
            'currency': row.currency,
            'name': row.price_book_name,
        }

    @classmethod
    async def listing(cls, db, user, query):
        await AdminScopeService.global_access(db, user, 'billing:price:read')
        rows, total = await PriceDao.page(db, query)
        return PageModel(
            rows=[cls.book(row) for row in rows],
            total=total,
            pageNum=query.page_num,
            pageSize=query.page_size,
            hasNext=query.page_num * query.page_size < total,
        )

    @classmethod
    async def create(cls, db, user, payload, key):
        path, prefix = '/price-books', '/api/admin/v1'
        data = payload.model_dump(by_alias=True)
        try:
            await AdminScopeService.global_access(db, user, 'billing:price:write')
            await WriteService.lock(db, user, path, key, api_prefix=prefix)
            replay = await WriteService.replay(db, user, path, key, data, api_prefix=prefix)
            if replay:
                await db.commit()
                return replay, True
            scope = await PriceDao.variant_scope(db, payload.model_variant_id)
            if scope is None:
                WorkspaceService.conflict('MODEL_VARIANT_NOT_FOUND', '模型精确规格不存在')
            _, version, model = scope
            if payload.account_id:
                account = await PriceDao.account(db, payload.account_id)
                if account is None or account.connection_id != model.connection_id or account.region != version.region:
                    WorkspaceService.conflict('PRICE_ACCOUNT_SCOPE_MISMATCH', '采购账号必须属于模型连接及相同区域')
                if account.status != '0':
                    WorkspaceService.conflict('PRICE_ACCOUNT_DISABLED', '停用账号不能新增采购价格簿')
            if await PriceDao.existing(db, payload):
                WorkspaceService.conflict('PRICE_BOOK_EXISTS', '此规格、用途、账号和币种的价格簿已存在')
            row = await PriceDao.add(
                db,
                dict(
                    model_variant_id=int(payload.model_variant_id),
                    purpose=payload.purpose,
                    account_id=int(payload.account_id) if payload.account_id else None,
                    currency=payload.currency,
                    price_book_name=payload.name,
                    **WriteService.audit(user),
                ),
            )
            return await WriteService.finish(
                db, user, path, key, data, cls.book(row), 'price_book', row.price_book_id, api_prefix=prefix
            )
        except Exception:
            await db.rollback()
            raise
