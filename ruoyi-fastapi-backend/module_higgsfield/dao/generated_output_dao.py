"""批量归档统计从输出事实读取，逻辑删除不影响历史任务完整性。"""

from sqlalchemy import select, func, or_, and_
from module_higgsfield.entity.do.generated_output_do import HfGeneratedOutput
from module_higgsfield.entity.do.job_do import HfCreationJob
from module_higgsfield.entity.do.asset_do import HfStoredFile


class GeneratedOutputDao:
    @staticmethod
    async def card_previews(db, job_ids):
        """每任务只取首个就绪媒体，批量查询不发布供应商源地址。"""
        if not job_ids:
            return {}
        rows = (await db.execute(
            select(HfGeneratedOutput.job_id, HfGeneratedOutput.output_id,
                   HfGeneratedOutput.revision, HfGeneratedOutput.kind)
            .join(HfStoredFile, HfStoredFile.file_id == HfGeneratedOutput.file_id)
            .where(
                HfGeneratedOutput.job_id.in_(job_ids), HfGeneratedOutput.del_flag == '0',
                HfGeneratedOutput.archive_state == '2', HfStoredFile.state == '1',
                or_(
                    and_(HfGeneratedOutput.kind == 'image', HfStoredFile.mime_type.in_(('image/png', 'image/jpeg', 'image/webp', 'image/gif'))),
                    and_(HfGeneratedOutput.kind == 'video', HfStoredFile.mime_type.in_(('video/mp4', 'video/webm'))),
                ),
            )
            .distinct(HfGeneratedOutput.job_id)
            .order_by(HfGeneratedOutput.job_id, HfGeneratedOutput.ordinal, HfGeneratedOutput.output_id)
        )).all()
        return {row.job_id: {'outputId': str(row.output_id), 'revision': str(row.revision), 'kind': row.kind} for row in rows}

    @staticmethod
    async def archive_candidates(db, now, limit):
        """只读取候选编号与版本；实际占用仍按任务→输出加锁，避免锁顺序倒置。"""
        return (
            await db.execute(
                select(HfGeneratedOutput.output_id, HfGeneratedOutput.revision)
                .where(
                    HfGeneratedOutput.del_flag == '0',
                    HfGeneratedOutput.kind.in_(('image', 'video')),
                    HfGeneratedOutput.source_url_ciphertext.is_not(None),
                    HfGeneratedOutput.archive_state.in_(('0', '1', '3')),
                    or_(HfGeneratedOutput.next_retry_time.is_(None), HfGeneratedOutput.next_retry_time <= now),
                )
                .order_by(HfGeneratedOutput.next_retry_time.asc().nullsfirst(), HfGeneratedOutput.output_id)
                .limit(limit)
            )
        ).all()

    @staticmethod
    async def get(db, identity):
        return await db.scalar(select(HfGeneratedOutput).where(HfGeneratedOutput.output_id == identity))

    @staticmethod
    async def locked(db, output_id):
        job_id = await db.scalar(select(HfGeneratedOutput.job_id).where(HfGeneratedOutput.output_id == output_id))
        if job_id is None:
            return None, None
        job = await db.scalar(
            select(HfCreationJob)
            .where(HfCreationJob.job_id == job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        output = await db.scalar(
            select(HfGeneratedOutput)
            .where(HfGeneratedOutput.output_id == output_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return job, output

    @staticmethod
    async def file(db, identity):
        return await db.scalar(
            select(HfStoredFile)
            .where(HfStoredFile.file_id == identity)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    @staticmethod
    async def for_job(db, job_id):
        return list(
            (
                await db.scalars(
                    select(HfGeneratedOutput)
                    .where(HfGeneratedOutput.job_id == job_id)
                    .order_by(HfGeneratedOutput.ordinal)
                )
            ).all()
        )

    @staticmethod
    async def add(db, values):
        row = HfGeneratedOutput(**values)
        db.add(row)
        await db.flush()
        return row

    @staticmethod
    async def archive_summaries(db, job_ids):
        if not job_ids:
            return {}
        rows = (
            await db.execute(
                select(
                    HfGeneratedOutput.job_id,
                    HfGeneratedOutput.archive_state,
                    func.count(),
                )
                .where(HfGeneratedOutput.job_id.in_(job_ids))
                .group_by(
                    HfGeneratedOutput.job_id,
                    HfGeneratedOutput.archive_state,
                )
            )
        ).all()
        result = {identity: dict(total=0, ready=0, failed=0, pending=0) for identity in job_ids}
        for identity, state, count in rows:
            result[identity]['total'] += count
            category = 'ready' if state in {'2', '5'} else 'failed' if state in {'3', '4'} else 'pending'
            result[identity][category] += count
        return result
