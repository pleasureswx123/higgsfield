"""项目与成本中心汇总参数不可混用，制作端不能扩大管理费用范围。"""

import unittest
from pydantic import ValidationError
from module_higgsfield.entity.vo.usage_query_vo import UsageQuery, StudioUsageQuery


class UsageQueryTests(unittest.TestCase):
    def test_scope_and_group_filters_are_explicit(self):
        base = {'from': '2026-11-01T00:00:00+08:00', 'to': '2026-11-02T00:00:00+08:00',
                'purpose': 'platform', 'scope': 'cost_center', 'groupBy': 'cost_center'}
        self.assertEqual(UsageQuery.model_validate(base | {'costCenterId': '9007199254740993'}).cost_center_id,
                         '9007199254740993')
        self.assertEqual(UsageQuery.model_validate(base | {'groupBy': 'day'}).group_by, 'day')
        for change in ({'groupBy': 'project'}, {'projectId': '1'}, {'userId': '1'},
                       {'departmentId': '1'}, {'modelId': '1'}, {'scope': 'project'},
                       {'scope': 'project', 'groupBy': 'day', 'costCenterId': '1'}):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                UsageQuery.model_validate(base | change)
        with self.assertRaises(ValidationError):
            StudioUsageQuery.model_validate(base)
