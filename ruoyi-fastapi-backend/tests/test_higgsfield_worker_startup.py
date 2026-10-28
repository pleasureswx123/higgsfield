"""工作器默认关闭消费；启动检查不连接数据库或供应商。"""

import argparse
import asyncio
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from module_higgsfield import worker


class WorkerStartupTests(unittest.TestCase):
    def test_all_modes_reject_without_explicit_enable(self):
        for mode in ('video', 'image', 'archive', 'image-recovery', 'billing',
                     'credential-test', 'reconciliation', 'element-import', 'image-thumbnail'):
            with self.subTest(mode=mode):
                result = subprocess.run(
                    [sys.executable, '-m', 'module_higgsfield.worker', '--mode', mode, '--once'],
                    cwd=Path(__file__).resolve().parents[1], capture_output=True,
                    encoding='utf-8', env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}, timeout=10,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn('任务消费默认关闭', result.stderr)
                self.assertEqual(result.stdout, '')

    def test_explicit_enable_preserves_mode_and_once(self):
        with patch.object(sys, 'argv', ['worker', '--enable-consumption', '--mode', 'billing', '--once']):
            options = worker.arguments()
        self.assertTrue(options.enable_consumption)
        self.assertTrue(options.once)
        self.assertEqual(options.mode, 'billing')

    def test_direct_run_rejects_before_framework_import(self):
        original = __import__

        def guarded_import(name, *args, **kwargs):
            if name.startswith(('config.', 'module_higgsfield.service.')):
                self.fail('关闭消费时不能加载运行配置或业务工作器')
            return original(name, *args, **kwargs)

        with patch('builtins.__import__', side_effect=guarded_import):
            for options in (argparse.Namespace(), argparse.Namespace(enable_consumption=False)):
                with self.assertRaisesRegex(ValueError, '任务消费默认关闭'):
                    asyncio.run(worker.run(options))

    def test_help_remains_available_without_enable(self):
        result = subprocess.run(
            [sys.executable, '-m', 'module_higgsfield.worker', '--help'],
            cwd=Path(__file__).resolve().parents[1], capture_output=True,
            encoding='utf-8', env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}, timeout=10,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn('--enable-consumption', result.stdout)
        self.assertEqual(result.stderr, '')
