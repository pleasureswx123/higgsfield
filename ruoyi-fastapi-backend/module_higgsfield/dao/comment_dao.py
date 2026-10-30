"""固定媒体评论的数据访问；不承担业务权限或事务提交。"""
from sqlalchemy import select, func, delete
from module_higgsfield.entity.do.comment_do import HfCommentThread, HfComment, HfAnnotation, HfCommentReaction


class CommentDao:
    @staticmethod
    async def asset_version_counts(db, version_ids):
        """批量统计当前版本有效评论，含回复，不含已删除讨论。"""
        if not version_ids:
            return {}
        query = (select(HfCommentThread.asset_version_id, func.count(HfComment.comment_id))
            .join(HfComment, HfComment.thread_id == HfCommentThread.thread_id)
            .where(HfCommentThread.asset_version_id.in_(version_ids),
                   HfCommentThread.del_flag == '0', HfComment.del_flag == '0')
            .group_by(HfCommentThread.asset_version_id))
        return dict((await db.execute(query)).all())

    @staticmethod
    async def clear_annotations(db, comment_id):
        await db.execute(delete(HfAnnotation).where(HfAnnotation.comment_id == comment_id))

    @staticmethod
    async def thread(db, identity, lock=False):
        query = select(HfCommentThread).where(HfCommentThread.thread_id == identity).execution_options(populate_existing=True)
        return await db.scalar(query.with_for_update() if lock else query)

    @staticmethod
    async def comment(db, identity, lock=False):
        query = select(HfComment).where(HfComment.comment_id == identity).execution_options(populate_existing=True)
        return await db.scalar(query.with_for_update() if lock else query)

    @staticmethod
    async def threads(db, target, page):
        condition = (HfCommentThread.asset_version_id == int(target.asset_version_id)
                     if target.asset_version_id else HfCommentThread.output_id == int(target.output_id))
        query = select(HfCommentThread).where(condition, HfCommentThread.del_flag == '0')
        total = await db.scalar(select(func.count()).select_from(query.subquery()))
        rows = (await db.scalars(query.order_by(HfCommentThread.create_time.desc(), HfCommentThread.thread_id.desc())
                .offset((page.page_num - 1) * page.page_size).limit(page.page_size))).all()
        return rows, total

    @staticmethod
    async def comments(db, thread_id, page):
        query = select(HfComment).where(HfComment.thread_id == thread_id)
        total = await db.scalar(select(func.count()).select_from(query.subquery()))
        rows = (await db.scalars(query.order_by(HfComment.create_time, HfComment.comment_id)
                .offset((page.page_num - 1) * page.page_size).limit(page.page_size))).all()
        return rows, total

    @staticmethod
    async def annotations(db, comment_id):
        return (await db.scalars(select(HfAnnotation).where(HfAnnotation.comment_id == comment_id)
                                .order_by(HfAnnotation.annotation_id))).all()

    @staticmethod
    async def reactions(db, comment_id):
        return (await db.scalars(select(HfCommentReaction).where(HfCommentReaction.comment_id == comment_id, HfCommentReaction.del_flag == '0'))).all()

    @staticmethod
    async def reaction(db, comment_id, user_id, emoji):
        return await db.scalar(select(HfCommentReaction).where(HfCommentReaction.comment_id == comment_id, HfCommentReaction.user_id == user_id, HfCommentReaction.emoji == emoji).with_for_update())
