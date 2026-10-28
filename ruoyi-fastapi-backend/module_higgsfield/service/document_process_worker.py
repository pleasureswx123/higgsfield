"""受限文档子进程；只输出有界JSON，不输出正文异常。"""
import ctypes
import json
import os
from pathlib import Path
import sys

_job_handle = None


def limit_memory(limit):
    """解析前建立内存限制，建立失败则拒绝继续。"""
    global _job_handle
    if os.name != 'nt':
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        return
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [('process_time', ctypes.c_longlong), ('job_time', ctypes.c_longlong),
            ('flags', wintypes.DWORD), ('min_working_set', ctypes.c_size_t), ('max_working_set', ctypes.c_size_t),
            ('active_processes', wintypes.DWORD), ('affinity', ctypes.c_size_t),
            ('priority', wintypes.DWORD), ('scheduling', wintypes.DWORD)]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [('basic', BasicLimits), ('io', IoCounters), ('process_memory', ctypes.c_size_t),
            ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateJobObjectW(None, None)
    limits = ExtendedLimits()
    limits.basic.flags = 0x100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY。
    limits.process_memory = limit
    if not handle or not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        if handle:
            kernel.CloseHandle(handle)
        raise OSError('无法设置内存限制')
    if not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess()):
        kernel.CloseHandle(handle)
        raise OSError('无法隔离解析进程')
    _job_handle = handle


def main():
    try:
        source, output, byte_limit, memory_limit = sys.argv[1:]
        limit_memory(int(memory_limit))
        # -I不加载用户站点和PYTHONPATH，仅加入受控解析代码目录。
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from pdf_text_extractor import PdfContentService
        with open(source, 'rb') as handle:
            body = handle.read(int(byte_limit) + 1)
        pages = PdfContentService.pages(body, max_bytes=int(byte_limit))
        result = json.dumps(pages, ensure_ascii=False).encode('utf-8')
        if len(result) > 8 * 1024 * 1024:
            return 2
        Path(output).write_bytes(result)
        return 0
    except Exception:
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
