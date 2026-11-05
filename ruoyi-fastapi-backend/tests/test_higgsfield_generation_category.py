"""用只读 PostgreSQL CTE 验证分类，不创建或修改业务记录。"""
import os
import unittest

from sqlalchemy import select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import create_async_engine
from config.database import build_async_sqlalchemy_database_url
from module_higgsfield.dao.generation_read_dao import GenerationReadDao
from module_higgsfield.entity.do.job_do import HfCreationJob


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用数据库测试')
class GenerationCategoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_categories_are_disjoint_and_complete(self):
        # 排队、运行、成功、失败、待核查、阻止、取消、保存中、保存失败、源过期。
        fixture = """WITH hf_creation_job(job_id, orchestration_state, upstream_state) AS (
            VALUES (1,'0','0'),(2,'4','2'),(3,'5','3'),(4,'5','4'),(5,'3','6'),
                   (6,'6','0'),(7,'5','5'),(8,'5','3'),(9,'5','3'),(10,'5','3')
        ), hf_generated_output(output_id, job_id, archive_state) AS (
            VALUES (1,3,'2'),(2,8,'1'),(3,8,'0'),(4,9,'3'),(5,9,'1'),(6,10,'4')
        ) """
        engine = create_async_engine(build_async_sqlalchemy_database_url())
        try:
            async with engine.connect() as db:
                for category, expected in [('active', [1, 2, 8]), ('attention', [4, 5, 6, 9, 10]), ('done', [3, 7])]:
                    statement = select(HfCreationJob.job_id).where(
                        GenerationReadDao.category_condition(category)
                    ).order_by(HfCreationJob.job_id)
                    sql = str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}))
                    self.assertEqual(list((await db.scalars(text(fixture + sql))).all()), expected)
        finally:
            await engine.dispose()
