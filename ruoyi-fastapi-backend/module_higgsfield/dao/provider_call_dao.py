"""调用身份写入和任务提交意图查询。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from module_higgsfield.entity.do.provider_call_do import HfProviderCall


class ProviderCallDao:
    @staticmethod
    async def sending_polls(db: AsyncSession, job_id: int) -> list[HfProviderCall]:
        return list(
            await db.scalars(
                select(HfProviderCall)
                .where(
                    HfProviderCall.job_id == job_id,
                    HfProviderCall.state == '1',
                    HfProviderCall.operation == 'video_poll',
                )
                .order_by(HfProviderCall.call_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )

    @staticmethod
    async def sending_submissions(db: AsyncSession, job_id: int) -> list[HfProviderCall]:
        return list(
            await db.scalars(
                select(HfProviderCall)
                .where(
                    HfProviderCall.job_id == job_id,
                    HfProviderCall.state == '1',
                    HfProviderCall.operation.in_(('image', 'video_submit', 'chat')),
                )
                .order_by(HfProviderCall.call_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )

    @staticmethod
    async def locked(db: AsyncSession, call_id: int) -> HfProviderCall | None:
        return await db.scalar(
            select(HfProviderCall)
            .where(HfProviderCall.call_id == call_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    @staticmethod
    async def submission(db: AsyncSession, job_id: int) -> HfProviderCall | None:
        return await db.scalar(
            select(HfProviderCall)
            .where(HfProviderCall.job_id == job_id, HfProviderCall.operation.in_(('image', 'video_submit', 'chat')))
            .order_by(HfProviderCall.call_id)
            .limit(1)
        )

    @staticmethod
    async def add(db: AsyncSession, values: dict) -> HfProviderCall:
        row = HfProviderCall(**values)
        db.add(row)
        await db.flush()
        return row
