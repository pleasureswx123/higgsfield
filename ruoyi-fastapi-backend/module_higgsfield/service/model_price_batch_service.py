"""同步发布模型双账价格，任一规格失败则整批回滚，不修改历史价格正文。"""
from module_higgsfield.dao.price_version_dao import PriceVersionDao
from module_higgsfield.dao.price_publish_dao import PricePublishDao
from module_higgsfield.dao.generation_price_dao import GenerationPriceDao
from module_higgsfield.dao.job_lease_dao import JobLeaseDao
from module_higgsfield.dao.price_dao import PriceDao
from module_higgsfield.entity.vo.price_publish_vo import PricePublish
from module_higgsfield.service.price_publish_service import PricePublishService
from module_higgsfield.service.price_version_service import PriceVersionService
from module_higgsfield.service.admin_scope_service import AdminScopeService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService


class ModelPriceBatchService:
    @classmethod
    async def publish(cls, db, user, payload, key):
        path, prefix = '/model-prices/publish', '/api/admin/v1'
        data = payload.model_dump(by_alias=True, mode='json')
        try:
            await AdminScopeService.global_access(db, user, 'billing:price:publish')
            await WriteService.lock(db, user, path, key, api_prefix=prefix)
            replay = await WriteService.replay(db, user, path, key, data, api_prefix=prefix)
            if replay:
                await db.commit()
                return replay, True
            plans, pairs = [], {}
            for item in sorted(payload.items, key=lambda item: int(item.version_id)):
                version = await PriceVersionDao.version(db, item.version_id)
                book = await PricePublishDao.book(db, version.price_book_id) if version else None
                if book is None or book.currency != 'USD':
                    WorkspaceService.conflict('PRICE_BATCH_INVALID', '价格记录不存在或不是美元价格')
                details = await PriceVersionService.result_for(db, version)
                signature = (details['roundingMode'], details['calculationScale'],
                    sorted([{k: v for k, v in row.items() if k != 'id'} for row in details['items']],
                        key=lambda row: (row['itemCode'], row['quantityFrom'])))
                group = pairs.setdefault(book.model_variant_id, {})
                if book.purpose in group:
                    WorkspaceService.conflict('PRICE_BATCH_INVALID', '同一规格不可重复提交同用途价格')
                group[book.purpose] = signature
                plans.append((item, book, version))
            if any(set(pair) != {'platform', 'procurement'} or pair['platform'] != pair['procurement'] for pair in pairs.values()):
                WorkspaceService.conflict('PRICE_BATCH_INVALID', '每个规格必须同时提交相同的项目价和采购价')
            # 全部价格簿按固定顺序锁定；生成受理使用同一价格簿锁，不能读到半批价格。
            for variant_id in sorted(pairs):
                await PriceDao.variant_scope(db, variant_id)
            for account_id in sorted({book.account_id for _, book, _ in plans if book.account_id}):
                await PriceDao.account(db, account_id)
            for book_id in sorted({book.price_book_id for _, book, _ in plans}):
                await PriceVersionDao.book(db, book_id)
            now = await JobLeaseDao.now(db)
            now = now.replace(microsecond=now.microsecond // 1000 * 1000)
            results = []
            for item, book, version in plans:
                version = await PriceVersionDao.version(db, item.version_id, lock=True)
                WorkspaceService.check_revision(version, item.revision)
                active = await GenerationPriceDao.active(db, book.price_book_id, now)
                old = active[0][0] if len(active) == 1 else None
                if len(active) > 1 or (str(old.activation_id) if old else None) != item.expected_activation_id:
                    WorkspaceService.conflict('PRICE_CHANGED', '价格已被其他管理员更新，请刷新页面后重新确认')
                if old and old.price_version_id == version.price_version_id:
                    continue
                request = PricePublish(revision=item.revision, effectiveFrom=now, reason=payload.reason,
                    replaceActivationId=str(old.activation_id) if old else None,
                    expectedActivationRevision=str(old.revision) if old else None)
                results.append(await PricePublishService.publish(db, user, item.version_id, request, key, batch=True))
            return await WriteService.finish(db, user, path, key, data, {'prices': results, 'effectiveFrom': now.isoformat()},
                'model_prices', int(payload.items[0].version_id), api_prefix=prefix)
        except Exception:
            await db.rollback()
            raise
