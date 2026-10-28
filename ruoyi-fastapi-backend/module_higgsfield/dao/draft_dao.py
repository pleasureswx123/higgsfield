from sqlalchemy import select, delete, func
from module_higgsfield.entity.do.draft_do import HfPromptDraft, HfDraftReference


class DraftDao:
    @staticmethod
    async def page(db, owner_id, query):
        statement = select(HfPromptDraft).where(
            HfPromptDraft.owner_id == owner_id, HfPromptDraft.project_id == int(query.project_id)
        )
        if query.kind:
            statement = statement.where(HfPromptDraft.kind == query.kind)
        total = await db.scalar(select(func.count()).select_from(statement.subquery()))
        rows = (
            await db.scalars(
                statement.order_by(HfPromptDraft.update_time.desc(), HfPromptDraft.draft_id.desc())
                .offset((query.page_num - 1) * query.page_size)
                .limit(query.page_size)
            )
        ).all()
        return rows, total

    @staticmethod
    async def get(db, draft_id):
        return await db.scalar(
            select(HfPromptDraft).where(HfPromptDraft.draft_id == draft_id).execution_options(populate_existing=True)
        )

    @staticmethod
    async def references(db, draft_id):
        return (
            await db.scalars(
                select(HfDraftReference).where(HfDraftReference.draft_id == draft_id).order_by(HfDraftReference.ordinal)
            )
        ).all()

    @staticmethod
    async def replace_references(db, draft_id, references, audit):
        # 草稿关系随保存替换；任务快照和历史证据不使用此删除路径。
        await db.execute(delete(HfDraftReference).where(HfDraftReference.draft_id == draft_id))
        for item in references:
            db.add(
                HfDraftReference(
                    draft_id=draft_id,
                    reference_key=int(item.reference_key),
                    asset_version_id=int(item.asset_version_id),
                    element_revision_id=int(item.element_revision_id) if item.element_revision_id else None,
                    media_role=item.media_role,
                    ordinal=item.ordinal,
                    **audit,
                )
            )
        await db.flush()

    @staticmethod
    async def add(db, **values):
        row = HfPromptDraft(**values)
        db.add(row)
        await db.flush()
        return row
