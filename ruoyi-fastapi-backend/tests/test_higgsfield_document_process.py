"""真实子进程超时、内存限制、结果边界与临时文件回收。"""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import psutil
from module_higgsfield.service.document_process_service import DocumentProcessService as Runner
from tests.test_higgsfield_element_pdf_parser import pdf_pages


class DocumentProcessTests(unittest.TestCase):
    def run_script(self, script, *, timeout=5, memory=128 * 1024 * 1024):
        processes, paths = [], []
        original = subprocess.Popen

        def launch(args, **kwargs):
            process = original(args, **kwargs)
            processes.append(process)
            paths.append(Path(args[4]).parent)
            return process

        with tempfile.TemporaryDirectory() as directory:
            worker = Path(directory) / 'worker.py'
            worker.write_text(script, encoding='utf-8')
            try:
                with patch.object(Runner, 'worker', worker), patch('subprocess.Popen', side_effect=launch):
                    return Runner.pdf_pages(b'%PDF-test', max_bytes=100, timeout=timeout, memory_bytes=memory)
            finally:
                self.assertEqual(len(processes), 1)
                self.assertIsNotNone(processes[0].poll())
                self.assertFalse(psutil.pid_exists(processes[0].pid))
                self.assertFalse(paths[0].exists())

    def test_deadline_kills_and_reaps_stalled_child(self):
        with self.assertRaisesRegex(ValueError, '超时'):
            self.run_script('import time\ntime.sleep(60)', timeout=0.2)

    def test_os_memory_limit_blocks_allocation(self):
        folder = str(Runner.worker.parent.resolve())
        script = f'import sys\nsys.path.insert(0, {folder!r})\n'
        script += 'from document_process_worker import limit_memory\nfrom pathlib import Path\n'
        script += 'limit_memory(64 * 1024 * 1024)\ntry:\n data = bytearray(256 * 1024 * 1024)\n'
        script += 'except MemoryError:\n Path(sys.argv[2]).write_text(\'["limited"]\')\n'
        self.assertEqual(self.run_script(script), ['limited'])

    def test_oversized_and_invalid_output_rejected_and_cleaned(self):
        for script in [
            'import sys\nfrom pathlib import Path\nPath(sys.argv[2]).write_bytes(b"x" * (8*1024*1024+1))',
            'import sys\nfrom pathlib import Path\nPath(sys.argv[2]).write_text(\'{"not":"pages"}\')',
            'raise SystemExit(2)',
        ]:
            with self.subTest(script=script[:20]), self.assertRaises(ValueError):
                self.run_script(script)

    def test_actual_pdf_is_read_in_child(self):
        result = Runner.pdf_pages(pdf_pages(['角色：记者']), max_bytes=100000)
        self.assertIn('角色：记者', result[0])
