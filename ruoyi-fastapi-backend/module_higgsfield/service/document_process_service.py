"""解析子进程监督；超时/超限终止并等待退出后删除临时文件。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import psutil


class DocumentProcessService:
    worker = Path(__file__).with_name('document_process_worker.py')

    @classmethod
    def pdf_pages(cls, body, *, max_bytes, timeout=30, memory_bytes=768 * 1024 * 1024):
        if (not isinstance(body, bytes) or not body or type(max_bytes) is not int or max_bytes <= 0
                or len(body) > max_bytes or not body.startswith(b'%PDF-')
                or not 0 < timeout <= 300 or type(memory_bytes) is not int or memory_bytes < 32 * 1024 * 1024):
            raise ValueError('解析输入或资源限制无效')
        with tempfile.TemporaryDirectory(prefix='hf-document-') as directory:
            source, output = Path(directory) / 'source.bin', Path(directory) / 'result.json'
            source.write_bytes(body)
            process = subprocess.Popen([sys.executable, '-I', str(cls.worker), str(source), str(output),
                str(max_bytes), str(memory_bytes)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            try:
                try:
                    watched = psutil.Process(process.pid)
                except psutil.NoSuchProcess:
                    watched = None
                deadline = time.monotonic() + timeout
                while process.poll() is None:
                    if time.monotonic() >= deadline:
                        raise ValueError('文档解析超时')
                    try:
                        if watched is not None and watched.memory_info().rss > memory_bytes:
                            raise ValueError('文档解析内存超限')
                    except psutil.NoSuchProcess:
                        pass
                    if output.exists() and output.stat().st_size > 8 * 1024 * 1024:
                        raise ValueError('解析结果大小超限')
                    time.sleep(0.02)
                if process.returncode != 0 or not output.exists() or output.stat().st_size > 8 * 1024 * 1024:
                    raise ValueError('PDF解析失败或资源超限')
                result = json.loads(output.read_bytes())
                if (not isinstance(result, list) or not 1 <= len(result) <= 200
                        or any(not isinstance(page, str) for page in result)
                        or sum(len(page) for page in result) > 2000000):
                    raise ValueError('PDF解析结果无效')
                return result
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()
