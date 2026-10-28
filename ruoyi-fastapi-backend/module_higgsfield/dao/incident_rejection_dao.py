"""已有受理或输出事实不能被人工拒绝结论覆盖。"""
from sqlalchemy import text


class IncidentRejectionDao:
    @staticmethod
    async def candidate(db, identity):
        return (await db.execute(text("""SELECT * FROM hf_provider_call WHERE job_id=:id
            AND operation='video_poll' AND state='2' AND response_metadata->>'acceptance'='rejected'
            ORDER BY call_id DESC LIMIT 1"""), {'id': identity})).first()

    @staticmethod
    async def contradictory(db, identity):
        return bool(await db.scalar(text("""SELECT
            EXISTS(SELECT 1 FROM hf_generated_output WHERE job_id=:id)
            OR EXISTS(SELECT 1 FROM hf_provider_call WHERE job_id=:id AND acceptance='accepted')
            OR (SELECT count(*) FROM hf_provider_call WHERE job_id=:id AND operation IN ('image','video_submit'))<>1
            """), {'id': identity}))
