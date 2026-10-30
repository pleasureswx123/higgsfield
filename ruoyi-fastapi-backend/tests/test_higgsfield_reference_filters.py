"""验证候选筛选 SQL 的授权条件、来源追溯和分页顺序。"""
import unittest
from sqlalchemy.dialects import postgresql
from module_higgsfield.dao.reference_dao import ReferenceDao
from module_higgsfield.entity.vo.reference_vo import ReferenceQuery

class QueryRecorder:
    def __init__(self):
        self.statements = []
    async def scalar(self, statement):
        self.statements.append(statement)
        return 0
    async def execute(self, statement):
        self.statements.append(statement)
        return self
    def mappings(self):
        return self
    def all(self):
        return []

class ReferenceFilterTests(unittest.IsolatedAsyncioTestCase):
    async def query(self, **options):
        db = QueryRecorder()
        await ReferenceDao.search(db, 1, 2, {'asset:read': 'own', 'asset:reference': 'own', 'element:read': 'own'}, ReferenceQuery(projectId='1', **options))
        return [str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True})) for statement in db.statements]

    async def test_asset_filters_are_applied_before_count_and_page(self):
        count, page = await self.query(kind='asset', source='uploaded', mediaType='video', recent=True, sort='oldest', pageNum=2, pageSize=12)
        for sql in (count, page):
            self.assertIn('WITH RECURSIVE reference_origin', sql)
            self.assertIn('hf_upload_binding', sql)
            self.assertIn("hf_asset.media_type = 'video'", sql)
            self.assertIn('hf_asset.create_user_id = 2', sql)
            self.assertIn('hf_asset.create_time >=', sql)
        self.assertNotIn('LIMIT', count)
        self.assertIn('created ASC', page)
        self.assertIn('LIMIT 12 OFFSET 12', page)

    async def test_element_category_and_name_sort(self):
        count, page = await self.query(kind='element', category='character', sort='name')
        self.assertIn("hf_element.category = 'character'", count)
        self.assertIn('hf_element.create_user_id = 2', count)
        self.assertIn('name ASC', page)

    async def test_generated_source_tracks_copies(self):
        count, _ = await self.query(kind='asset', source='generated')
        self.assertIn('source_asset_version_id', count)
        self.assertIn('source_output_id IS NOT NULL', count)

if __name__ == '__main__':
    unittest.main()
