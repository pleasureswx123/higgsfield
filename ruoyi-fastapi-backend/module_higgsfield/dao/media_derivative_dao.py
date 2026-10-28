"""派生任务数据库访问，调用方管理事务。"""
from sqlalchemy import select, func, or_, and_, exists
from sqlalchemy.dialects.postgresql import insert
from module_higgsfield.entity.do.asset_do import HfStoredFile
from module_higgsfield.entity.do.asset_do import HfAssetVersion
from module_higgsfield.entity.do.generated_output_do import HfGeneratedOutput
from module_higgsfield.entity.do.media_derivative_do import HfMediaDerivative as Row


class MediaDerivativeDao:
    @staticmethod
    async def undiscovered(db, recipe, limit):
        return list(await db.scalars(select(HfStoredFile.file_id).where(
            HfStoredFile.state == '1', HfStoredFile.mime_type.in_(('image/png', 'image/jpeg', 'image/webp')),
            ~exists(select(Row.derivative_id).where(Row.source_file_id == HfStoredFile.file_id, Row.recipe == recipe)),
            ~exists(select(Row.derivative_id).where(Row.derived_file_id == HfStoredFile.file_id)),
            or_(exists(select(HfAssetVersion.version_id).where(HfAssetVersion.file_id == HfStoredFile.file_id)),
                exists(select(HfGeneratedOutput.output_id).where(HfGeneratedOutput.file_id == HfStoredFile.file_id,
                    HfGeneratedOutput.archive_state == '2'))))
            .order_by(HfStoredFile.file_id).limit(limit)))

    @staticmethod
    async def by_key(db, key):
        return await db.scalar(select(HfStoredFile).where(HfStoredFile.storage_key == key))

    @staticmethod
    async def now(db):
        return await db.scalar(select(func.clock_timestamp()))

    @staticmethod
    async def file(db, identity, lock=False):
        query = select(HfStoredFile).where(HfStoredFile.file_id == identity).execution_options(populate_existing=True)
        return await db.scalar(query.with_for_update() if lock else query)

    @staticmethod
    async def enqueue(db, source_id, recipe, now, actor):
        await db.execute(insert(Row).values(source_file_id=source_id, recipe=recipe, next_action_time=now,
            create_by=actor, update_by=actor, create_time=now, update_time=now)
            .on_conflict_do_nothing(index_elements=['source_file_id', 'recipe']))
        return await db.scalar(select(Row).where(Row.source_file_id == source_id, Row.recipe == recipe))

    @staticmethod
    async def candidate(db, recipe, now):
        return await db.scalar(select(Row).where(Row.recipe == recipe, or_(
            and_(Row.state.in_(('0', '3')), Row.next_action_time <= now),
            and_(Row.state == '1', Row.lease_until <= now)))
            .order_by(Row.next_action_time, Row.derivative_id).limit(1)
            .with_for_update(skip_locked=True).execution_options(populate_existing=True))

    @staticmethod
    async def locked(db, identity):
        return await db.scalar(select(Row).where(Row.derivative_id == identity)
            .with_for_update().execution_options(populate_existing=True))

    @staticmethod
    async def ready(db, source_id, recipe):
        return await db.scalar(select(HfStoredFile).join(Row, Row.derived_file_id == HfStoredFile.file_id)
            .where(Row.source_file_id == source_id, Row.recipe == recipe, Row.state == '2', HfStoredFile.state == '1'))
