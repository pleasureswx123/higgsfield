"""把平台目录单向投影到 NAS；媒体使用同卷硬链接，共享同一份文件内容。"""

import asyncio
import json
import mimetypes
import os
import re
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path, PureWindowsPath
from uuid import uuid4

from config.database import DataSourceRegistry
from module_higgsfield.dao.nas_directory_dao import NasDirectoryDao
from module_higgsfield.service.storage_service import StorageService
from utils.log_util import logger


def safe_name(value):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', unicodedata.normalize('NFKC', value))
    name = name.strip().rstrip('. ')[:90].rstrip('. ') or '未命名'
    return '_' + name if PureWindowsPath(name).is_reserved() or name.startswith('.') else name


def child(root, relative):
    """逐层拒绝越界、符号链接和 Windows 重解析点。"""
    current = root
    for part in relative.split('/'):
        if not part or part in ('.', '..') or re.search(r'[\\:/]', part):
            raise ValueError('目录映射包含无效路径')
        current = current / part
        if current.is_symlink() or (current.exists() and StorageService.is_reparse(current)):
            raise ValueError('目录映射经过链接')
    return current


@contextmanager
def directory_lock(root):
    """进程重启时系统释放文件锁，多实例只允许一方写目录清单。"""
    with child(root, 'directory.lock').open('a+b') as handle:
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (PermissionError, BlockingIOError):
            yield False
            return
        yield True


class NasDirectoryService:
    def __init__(self, storage):
        self.storage = storage
        self.objects = storage.verify_root()
        if storage.policy.mode != 'nas' or self.objects.name != '.platform':
            raise ValueError('项目目录同步要求 NAS 存储根目录为环境目录下的 .platform')
        self.root = self.objects.parent
        if self.root.name != os.environ.get('APP_ENV', 'dev'):
            raise ValueError('NAS 环境目录与运行环境不一致')

    def source(self, key):
        if not re.fullmatch(r'media/[a-f0-9]{32}', key):
            raise ValueError('媒体存储键无效')
        return child(self.objects, key)

    def retire_directory(self, path):
        """保留外部文件。仅有资源管理器缩略图缓存时将旧目录完整移入内部目录。"""
        if not path.is_dir():
            return
        contents = list(path.iterdir())
        if not contents:
            path.rmdir()
        elif len(contents) == 1 and contents[0].name.casefold() == 'thumbs.db':
            cache = child(path, contents[0].name)
            if cache.is_file():
                archive = child(self.objects, 'retired-thumbnail-caches')
                archive.mkdir(exist_ok=True)
                path.rename(archive / uuid4().hex)

    def sync(self, rows):
        with directory_lock(self.objects) as acquired:
            if acquired:
                self._sync(rows)

    def _sync(self, rows, database=None):
        manifest = child(self.objects, 'directory.json')
        state = json.loads(manifest.read_text('utf-8')) if manifest.exists() else {}
        binding = state.get('database')
        if binding and database != binding:
            raise ValueError('NAS 目录已绑定到其他数据库或模式')
        previous = state.get('entries', {})
        retired = list(state.get('retired', []))
        desired = {}
        claimed = {}
        by_id = {f"{r['kind']}-{r['id']}": r for r in rows}
        visiting = set()

        def allocate(identity):
            if identity in desired:
                return desired[identity]['path']
            if identity in visiting:
                raise ValueError('项目文件夹层级循环')
            visiting.add(identity)
            row = by_id[identity]
            kind, key = row['kind'], row['storage_key']
            old = previous.get(identity, {})
            name = safe_name(row['name'])
            parent = ''
            if kind == 'creator':
                name = old.get('path', name)
            elif kind == 'project':
                parent = allocate(f"creator-{row['parent']}") + '/'
                if old:
                    # 旧版只有项目一级，新旧映射都沿用首次分配的项目名。
                    name = old['path'].rsplit('/', 1)[-1]
            else:
                owner = f"folder-{row['parent']}" if row['parent'] else f"project-{row['project_id']}"
                if by_id[owner]['project_id'] != row['project_id']:
                    raise ValueError('目录归属项目不一致')
                parent = allocate(owner) + '/'
            ext = ''
            if key:
                mime = row['mime_type']
                ext = {'image/jpeg': '.jpg', 'text/markdown': '.md'}.get(mime) or mimetypes.guess_extension(mime) or '.bin'
                if Path(name).suffix.lower() in mimetypes.types_map or name.lower().endswith(ext):
                    name = Path(name).stem
            number = 1
            while True:
                suffix = '' if number == 1 else f'（{number}）'
                relative = f'{parent}{name}{suffix}{ext}'
                target = child(self.root, relative)
                same = old.get('path') == relative and old.get('key') == key
                if relative.casefold() not in claimed:
                    if not target.exists():
                        break
                    if same and not key and target.is_dir():
                        break
                    if same and key and (not self.source(key).exists() or target.samefile(self.source(key))):
                        break
                number += 1
            desired[identity] = {'path': relative, 'key': key}
            claimed[relative.casefold()] = identity
            visiting.remove(identity)
            return relative

        # 优先保留已有同名对象的编号，目录优先于文件。
        for identity in sorted(by_id, key=lambda i: (i not in previous, by_id[i]['storage_key'] is not None, i)):
            allocate(identity)
        for identity, old in previous.items():
            if old != desired.get(identity) and old not in retired:
                retired.append(old)

        def save(obsolete):
            tmp = child(self.objects, 'directory.json.tmp')
            tmp.write_text(json.dumps({'database': database, 'entries': desired, 'retired': obsolete}, ensure_ascii=False), 'utf-8')
            os.replace(tmp, manifest)

        # 先记录意图；中途断电或断网后，下轮按同一组路径继续。
        if binding != database or desired != previous or retired != state.get('retired', []) or not manifest.exists():
            save(retired)
        missing = []
        for entry in desired.values():
            target = child(self.root, entry['path'])
            if not entry['key']:
                target.mkdir(exist_ok=True)
                continue
            source = self.source(entry['key'])
            if not source.is_file():
                missing.append(entry['key'])
                continue
            if not target.exists():
                os.link(source, target)
            elif not target.samefile(source):
                raise ValueError('NAS 文件已被外部替换，请移走冲突文件后重试')

        if missing:
            raise FileNotFoundError(f'有 {len(missing)} 个媒体源文件缺失，已保留旧链接等待重试')

        for entry in sorted(retired, key=lambda e: e['path'].count('/'), reverse=True):
            if entry['path'].casefold() in claimed:
                continue
            path = child(self.root, entry['path'])
            if entry['key']:
                if path.exists() and path.samefile(self.source(entry['key'])):
                    path.unlink()
            else:
                self.retire_directory(path)
        if retired:
            save([])

    @classmethod
    async def run(cls, stop):
        last_entries = None
        next_check = 0
        while not stop.is_set():
            try:
                service = await asyncio.to_thread(cls, StorageService())
                # 锁覆盖快照读取和应用，避免较早取得的快照覆盖其他实例的新结果。
                lock = directory_lock(service.objects)
                acquired = await asyncio.to_thread(lock.__enter__)
                try:
                    if acquired:
                        async with DataSourceRegistry.session(log_sql=False) as db:
                            database = await NasDirectoryDao.database_identity(db)
                            entries = await NasDirectoryDao.entries(db)
                        if entries != last_entries or time.monotonic() >= next_check:
                            await asyncio.to_thread(service._sync, entries, database)
                            last_entries = entries
                            next_check = time.monotonic() + 60
                finally:
                    await asyncio.to_thread(lock.__exit__, None, None, None)
            except Exception:
                logger.exception('NAS 项目目录同步失败，将自动重试')
            try:
                await asyncio.wait_for(stop.wait(), timeout=5)
            except TimeoutError:
                pass
