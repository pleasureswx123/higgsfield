"""发布与结束区间共用价格簿行锁，保持价格正文及历史证据。"""

from common.vo import PageModel
from module_higgsfield.dao.price_publish_dao import PricePublishDao
from module_higgsfield.dao.price_version_dao import PriceVersionDao
from module_higgsfield.dao.price_dao import PriceDao
from module_higgsfield.entity.do.price_do import HfPriceActivation, HfPricePublishEvent
from module_higgsfield.service.admin_scope_service import AdminScopeService
from module_higgsfield.service.project_workspace_service import WorkspaceService
from module_higgsfield.service.write_service import WriteService
from module_higgsfield.service.price_version_service import PriceVersionService


class PricePublishService:
    fail = staticmethod(WorkspaceService.conflict)

    @staticmethod
    def activation(row):
        return {
            'id': str(row.activation_id),
            'priceBookId': str(row.price_book_id),
            'priceVersionId': str(row.price_version_id),
            'effectiveFrom': row.effective_from.isoformat(),
            'effectiveUntil': row.effective_until.isoformat() if row.effective_until else None,
            'revision': str(row.revision),
        }

    @staticmethod
    def update(row, audit):
        row.revision += 1
        row.update_by, row.update_time = audit['update_by'], audit['update_time']

    @classmethod
    async def event(cls, db, user, row, action, reason, before, audit):
        await PricePublishDao.add(
            db,
            HfPricePublishEvent,
            price_version_id=row.price_version_id,
            activation_id=row.activation_id,
            actor_id=user.user.user_id,
            action=action,
            reason=reason,
            diff={'before': before, 'after': cls.activation(row)},
            **audit,
        )

    @classmethod
    async def publish(cls, db, user, identity, payload, key):
        path, prefix = f'/price-versions/{identity}/publish', '/api/admin/v1'
        data = payload.model_dump(by_alias=True, mode='json')
        try:
            await AdminScopeService.global_access(db, user, 'billing:price:publish')
            await WriteService.lock(db, user, path, key, api_prefix=prefix)
            replay = await WriteService.replay(db, user, path, key, data, api_prefix=prefix)
            if replay:
                await db.commit()
                return replay, True
            version = await PriceVersionDao.version(db, identity)
            if version is None:
                cls.fail('PRICE_VERSION_NOT_FOUND', '价格版本不存在')
            book = await PricePublishDao.book(db, version.price_book_id)
            if book is None:
                cls.fail('PRICE_BOOK_NOT_FOUND', '价格簿不存在')
            # 与价格簿创建保持模型、账号、价格簿、价格版本的加锁顺序。
            scope = await PriceDao.variant_scope(db, book.model_variant_id)
            if scope is None or scope[1].status != '2':
                cls.fail('PRICE_MODEL_NOT_PUBLISHED', '价格发布要求对应模型能力已发布')
            if book.account_id:
                account = await PriceDao.account(db, book.account_id)
                if (
                    account is None
                    or account.status != '0'
                    or account.connection_id != scope[2].connection_id
                    or account.region != scope[1].region
                ):
                    cls.fail('PRICE_ACCOUNT_SCOPE_MISMATCH', '采购账号已失效或不匹配模型连接和区域')
            await PriceVersionDao.book(db, book.price_book_id)
            version = await PriceVersionDao.version(db, identity, lock=True)
            WorkspaceService.check_revision(version, payload.revision)
            details = await PriceVersionService.result_for(db, version)
            if details['validationIssues']:
                cls.fail('PRICE_VERSION_INCOMPLETE', '价格分项、阶梯或来源校验未通过')
            old = None
            if payload.replace_activation_id:
                old = await PricePublishDao.activation(db, payload.replace_activation_id, lock=True)
                if old is None or old.price_book_id != book.price_book_id:
                    cls.fail('PRICE_ACTIVATION_NOT_FOUND', '替换区间不存在或不属于此价格簿')
                WorkspaceService.check_revision(old, payload.expected_activation_revision)
                if payload.effective_from <= old.effective_from or (
                    old.effective_until is not None and payload.effective_from >= old.effective_until
                ):
                    cls.fail('PRICE_REPLACEMENT_RANGE_INVALID', '替换起点必须位于旧区间内部')
            if await PricePublishDao.overlap(
                db,
                book.price_book_id,
                payload.effective_from,
                payload.effective_until,
                old.activation_id if old else None,
            ):
                cls.fail('PRICE_ACTIVATION_OVERLAP', '同一价格簿的生效区间不能重叠')
            audit = WriteService.audit(user)
            if old:
                before = cls.activation(old)
                old.effective_until = payload.effective_from
                cls.update(old, audit)
                await cls.event(db, user, old, 'end_activation', payload.reason, before, audit)
            version.status = '1'
            cls.update(version, audit)
            row = await PricePublishDao.add(
                db,
                HfPriceActivation,
                price_book_id=book.price_book_id,
                price_version_id=version.price_version_id,
                effective_from=payload.effective_from,
                effective_until=payload.effective_until,
                **audit,
            )
            await cls.event(db, user, row, 'publish', payload.reason, None, audit)
            result = {'version': await PriceVersionService.result_for(db, version), 'activation': cls.activation(row)}
            return await WriteService.finish(
                db, user, path, key, data, result, 'price_activation', row.activation_id, api_prefix=prefix
            )
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def end(cls, db, user, identity, payload, key):
        path, prefix = f'/price-activations/{identity}/end', '/api/admin/v1'
        data = payload.model_dump(by_alias=True, mode='json')
        try:
            await AdminScopeService.global_access(db, user, 'billing:price:publish')
            await WriteService.lock(db, user, path, key, api_prefix=prefix)
            replay = await WriteService.replay(db, user, path, key, data, api_prefix=prefix)
            if replay:
                await db.commit()
                return replay, True
            row = await PricePublishDao.activation(db, identity)
            if row is None:
                cls.fail('PRICE_ACTIVATION_NOT_FOUND', '价格生效区间不存在')
            if await PriceVersionDao.book(db, row.price_book_id) is None:
                cls.fail('PRICE_BOOK_NOT_FOUND', '价格簿不存在')
            row = await PricePublishDao.activation(db, identity, lock=True)
            WorkspaceService.check_revision(row, payload.revision)
            if payload.effective_until <= row.effective_from or (
                row.effective_until is not None and payload.effective_until >= row.effective_until
            ):
                cls.fail('PRICE_END_RANGE_INVALID', '结束操作只能缩短区间且必须保留有效起点')
            before = cls.activation(row)
            audit = WriteService.audit(user)
            row.effective_until = payload.effective_until
            cls.update(row, audit)
            await cls.event(db, user, row, 'end_activation', payload.reason, before, audit)
            return await WriteService.finish(
                db, user, path, key, data, cls.activation(row), 'price_activation', row.activation_id, api_prefix=prefix
            )
        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def history(cls, db, user, identity, query):
        await AdminScopeService.global_access(db, user, 'billing:price:read')
        if await PriceVersionDao.version(db, identity) is None:
            cls.fail('PRICE_VERSION_NOT_FOUND', '价格版本不存在')
        rows, total = await PricePublishDao.history(db, identity, query)
        return PageModel(
            rows=[
                {
                    'id': str(row.publish_event_id),
                    'action': row.action,
                    'actorId': str(row.actor_id),
                    'reason': row.reason,
                    'diff': row.diff,
                    'createTime': row.create_time.isoformat(),
                }
                for row in rows
            ],
            total=total,
            pageNum=query.page_num,
            pageSize=query.page_size,
            hasNext=query.page_num * query.page_size < total,
        )
