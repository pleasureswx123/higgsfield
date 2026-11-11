"""固定版本的制作和审核证据，仅追加，不提供修改或删除。"""
from sqlalchemy import select
from module_higgsfield.entity.do.review_do import HfReviewEvent


class ReviewDao:
    @staticmethod
    def target(kind, target_id):
        if kind == 'asset':
            return HfReviewEvent.asset_id == target_id
        if kind == 'element':
            return HfReviewEvent.element_id == target_id
        raise ValueError('不支持的制作对象')

    @classmethod
    async def history(cls, db, kind, target_id):
        return (await db.scalars(select(HfReviewEvent).where(cls.target(kind, target_id))
                                .order_by(HfReviewEvent.review_event_id.desc()).limit(100))).all()

    @classmethod
    async def submitted(cls, db, kind, target_id, version_id):
        column = HfReviewEvent.asset_version_id if kind == 'asset' else HfReviewEvent.element_revision_id
        action = await db.scalar(select(HfReviewEvent.action).where(cls.target(kind, target_id), column == version_id)
                                 .order_by(HfReviewEvent.review_event_id.desc()).limit(1))
        return action == 'submit'

    @classmethod
    async def approved_version(cls, db, kind, target_id):
        column = HfReviewEvent.asset_version_id if kind == 'asset' else HfReviewEvent.element_revision_id
        return await db.scalar(select(column).where(cls.target(kind, target_id), HfReviewEvent.action == 'approve')
                               .order_by(HfReviewEvent.review_event_id.desc()).limit(1))

    @staticmethod
    async def record(db, *, kind, target_id, version_id, action, previous, status, user, reason=''):
        from module_higgsfield.service.write_service import WriteService
        row = HfReviewEvent(
            **({'asset_id': target_id, 'asset_version_id': version_id} if kind == 'asset' else
               {'element_id': target_id, 'element_revision_id': version_id}),
            action=action, actor_id=user.user.user_id, from_status=previous, to_status=status,
            reason=reason.strip() or None, **WriteService.audit(user),
        )
        db.add(row)
        await db.flush()
        return row
