"""图片运行配置拒绝缺失、非法和超硬上限容量。"""

import os
import unittest
from unittest.mock import patch

from module_higgsfield.service.image_worker_runtime import image_resources


class ImageRuntimePolicyTests(unittest.TestCase):
    def test_missing_and_invalid_environment_capacity(self) -> None:
        for value in ('', '-1', '0', '1.5', '１', '999999999999999999'):
            with (
                self.subTest(value=value),
                patch.dict(os.environ, {'HF_IMAGE_MAX_DECODED_BYTES': value}),
                self.assertRaises(ValueError),
            ):
                image_resources()

    def test_explicit_capacity_rejects_bool_and_float(self) -> None:
        for value in (True, 1.5, -1, 0, 268435456):
            with self.subTest(value=value), self.assertRaises(ValueError):
                image_resources(max_decoded_bytes=value)
