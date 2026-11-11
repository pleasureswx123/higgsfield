"""审核证据必须指向确切内容版本；历史数据不伪造版本。"""
import unittest

from module_higgsfield.entity.do.asset_do import HfAsset
from module_higgsfield.entity.do.review_do import HfReviewEvent
from module_higgsfield.entity.do.element_do import HfElementRevision


class ReviewEvidenceSchemaTests(unittest.TestCase):
    def test_element_version_preserves_reviewed_category(self):
        self.assertIn('category_snapshot', HfElementRevision.__table__.columns)
    def test_asset_can_be_assigned_without_changing_author(self):
        self.assertIn('performer_id', HfAsset.__table__.columns)
        self.assertIn('create_user_id', HfAsset.__table__.columns)

    def test_review_preserves_target_version_and_business_action(self):
        for name in ('asset_id', 'asset_version_id', 'element_revision_id', 'action'):
            with self.subTest(column=name):
                self.assertIn(name, HfReviewEvent.__table__.columns)

    def test_new_evidence_requires_matching_target_and_version(self):
        constraints = {item.name for item in HfReviewEvent.__table__.constraints}
        self.assertIn('ck_hf_review_version_target', constraints)
