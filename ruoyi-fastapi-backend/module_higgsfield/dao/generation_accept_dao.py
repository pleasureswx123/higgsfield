"""永久请求去重及任务固定引用写入。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from module_higgsfield.entity.do.job_do import HfCreationJob, HfJobReference


class GenerationAcceptDao:
    @staticmethod
    async def existing(db: AsyncSession, actor_id: int, project_id: int, key: str) -> HfCreationJob | None:
        return await db.scalar(
            select(HfCreationJob).where(
                HfCreationJob.actor_id == actor_id,
                HfCreationJob.project_id == project_id,
                HfCreationJob.idempotency_key == key,
            )
        )

    @staticmethod
    async def create(db: AsyncSession, values: dict, compiled: dict, audit: dict) -> HfCreationJob:
        job = HfCreationJob(**values, **audit)
        db.add(job)
        await db.flush()
        for media in compiled['media']:
            sources = [source for source in compiled['sources'] if source['compiledOrdinal'] == media['ordinal']]
            db.add(
                HfJobReference(
                    job_id=job.job_id,
                    asset_version_id=int(media['assetVersionId']),
                    element_revision_id=None,
                    media_role=media['mediaRole'],
                    ordinal=media['ordinal'],
                    reference_snapshot={**media, 'sources': sources},
                    **audit,
                )
            )
        await db.flush()
        return job
