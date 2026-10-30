"""视频画面标注校验，不连接数据库。"""
from decimal import Decimal
from types import SimpleNamespace
import unittest
from exceptions.exception import ServiceWarning
from module_higgsfield.service.comment_service import CommentService


class VideoCommentTests(unittest.TestCase):
    def payload(self, time=Decimal('1'), width=1920):
        return SimpleNamespace(video_time=time, annotations=[SimpleNamespace(source_width=width, source_height=1080)])

    def setUp(self):
        self.file = SimpleNamespace(state='1', seconds=Decimal('14'), width=1920, height=1080)

    def test_video_annotation_at_zero_and_valid_time(self):
        CommentService.validate_media('video', self.file, self.payload(Decimal('0')))
        CommentService.validate_media('video', self.file, self.payload())

    def test_video_annotation_requires_time_and_matching_dimensions(self):
        for payload in [self.payload(None), self.payload(Decimal('15')), self.payload(width=100)]:
            with self.assertRaises(ServiceWarning):
                CommentService.validate_media('video', self.file, payload)

    def test_image_annotations_still_work_without_time(self):
        CommentService.validate_media('image', self.file, self.payload(None))
