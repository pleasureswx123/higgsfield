"""响应证据仅新增和读取，不提供覆盖或删除入口。"""

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from module_higgsfield.entity.do.provider_response_do import HfProviderResponse
from module_higgsfield.entity.do.provider_call_do import HfProviderCall
from module_higgsfield.entity.do.generated_output_do import HfGeneratedOutput


class ProviderResponseDao:
    @staticmethod
    def completed_images():
        return (
            select(HfProviderResponse)
            .join(
                HfProviderCall,
                HfProviderCall.call_id == HfProviderResponse.provider_call_id,
            )
            .where(
                HfProviderCall.job_id == HfProviderResponse.job_id,
                HfProviderCall.operation == 'image',
                HfProviderCall.state == '2',
                HfProviderCall.acceptance == 'accepted',
            )
        )

    @classmethod
    async def for_completed_image(cls, db, job_id):
        return await db.scalar(
            cls.completed_images()
            .where(HfProviderResponse.job_id == job_id)
            .order_by(HfProviderResponse.response_evidence_id)
            .limit(1)
        )

    @classmethod
    async def recovery_candidates(cls, db, now, limit):
        evidence = cls.completed_images().where(HfProviderResponse.job_id == HfGeneratedOutput.job_id).exists()
        return (
            await db.execute(
                select(HfGeneratedOutput.output_id, HfGeneratedOutput.revision)
                .where(
                    HfGeneratedOutput.kind == 'image',
                    HfGeneratedOutput.del_flag == '0',
                    HfGeneratedOutput.archive_state.in_(('0', '1', '3')),
                    HfGeneratedOutput.source_url_ciphertext.is_(None),
                    or_(HfGeneratedOutput.next_retry_time.is_(None), HfGeneratedOutput.next_retry_time <= now),
                    evidence,
                )
                .order_by(HfGeneratedOutput.next_retry_time.asc().nullsfirst(), HfGeneratedOutput.output_id)
                .limit(limit)
            )
        ).all()

    @staticmethod
    async def for_call(db: AsyncSession, call_id: int) -> HfProviderResponse | None:
        return await db.scalar(select(HfProviderResponse).where(HfProviderResponse.provider_call_id == call_id))

    @staticmethod
    async def add(db: AsyncSession, values: dict) -> HfProviderResponse:
        row = HfProviderResponse(**values)
        db.add(row)
        await db.flush()
        return row
