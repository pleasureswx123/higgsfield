"""受控文件存储：显式配置、挂载核验、不可覆盖的随机存储键。"""

import hashlib
import json
import os
import re
import stat
import subprocess
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from exceptions.exception import ServiceWarning


@dataclass(frozen=True)
class StoragePolicy:
    root: str
    mode: str
    source: str
    max_bytes: int
    max_pixels: int
    ffprobe: str = 'ffprobe'
    part_size: int = 32 * 1024 * 1024

    @classmethod
    def from_environment(cls):
        """缺少容量策略时关闭上传，不把缺配置解释为无限制。"""
        try:
            policy = cls(
                root=os.environ['HF_STORAGE_ROOT'],
                mode=os.environ['HF_STORAGE_MODE'],
                source=os.environ.get('HF_NAS_SOURCE', ''),
                max_bytes=int(os.environ['HF_UPLOAD_MAX_BYTES']),
                max_pixels=int(os.environ['HF_IMAGE_MAX_PIXELS']),
                ffprobe=os.environ.get('HF_FFPROBE', 'ffprobe'),
            )
            if policy.max_bytes <= 0 or policy.max_pixels <= 0 or policy.mode not in ('nas', 'local-test'):
                raise ValueError
            if policy.mode == 'local-test' and os.environ.get('APP_ENV', 'dev').strip().lower() not in (
                'dev',
                'test',
                'local',
            ):
                raise ValueError
            return policy
        except (KeyError, ValueError):
            raise ServiceWarning(
                message='尚未配置有效存储和媒体限制', data={'errorCode': 'STORAGE_UNAVAILABLE'}
            ) from None


class StorageService:
    """阻塞文件操作由调用方放入线程；不持有数据库事务。"""

    def __init__(self, policy=None):
        self.policy = policy or StoragePolicy.from_environment()

    @staticmethod
    def is_reparse(path):
        return bool(getattr(path.lstat(), 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0))

    @staticmethod
    def unavailable():
        raise ServiceWarning(message='存储不可用，请稍后重试', data={'errorCode': 'STORAGE_UNAVAILABLE'})

    def verify_root(self):
        try:
            return self._verify_root()
        except OSError:
            self.unavailable()

    def _verify_root(self):
        root = Path(self.policy.root)
        if not root.is_absolute() or not root.is_dir() or root.is_symlink() or self.is_reparse(root):
            self.unavailable()
        if self.policy.mode == 'local-test':
            return root
        if self.policy.mode != 'nas' or not self.policy.source:
            self.unavailable()
        if os.name == 'nt':
            # UNC 直连共享不存在本地挂载点回落；不接受盘符映射。
            normalized = str(root).replace('/', '\\').casefold()
            source = self.policy.source.replace('/', '\\').rstrip('\\').casefold()
            if (
                not source.startswith('\\\\')
                or source.startswith(('\\\\?\\', '\\\\.\\'))
                or not normalized.startswith(source + '\\')
            ):
                self.unavailable()
        else:
            resolved = str(root.resolve())
            mounts = []
            try:
                for line in Path('/proc/self/mountinfo').read_text().splitlines():
                    before, after = line.split(' - ', 1)
                    fields, details = before.split(), after.split()
                    mount = re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), fields[4])
                    if resolved == mount or resolved.startswith(mount.rstrip('/') + '/'):
                        mounts.append((len(mount), details[0], details[1], fields[2]))
                _, filesystem, source, device = max(mounts)
                actual = root.stat().st_dev
                if filesystem not in ('cifs', 'nfs', 'nfs4') or source != self.policy.source:
                    self.unavailable()
                if f'{os.major(actual)}:{os.minor(actual)}' != device:
                    self.unavailable()
            except (OSError, ValueError):
                self.unavailable()
        return root

    @contextmanager
    def open_key(self, key, write=False):
        """Linux 用目录句柄遍历，持有挂载引用，防止断挂后落到本地同名目录。"""
        if not re.fullmatch(r'(upload-staging|media|provider-evidence)/[a-f0-9]{32}', key):
            raise ValueError('非法内部存储键')
        directory, name = key.split('/')
        root = self.verify_root()
        handle = None
        descriptors = []
        try:
            if os.name != 'nt':
                root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                descriptors.append(root_fd)
                if os.fstat(root_fd).st_dev != root.stat().st_dev:
                    self.unavailable()
                # 打开后再次核验，随后所有操作均相对已持有的目录句柄。
                self.verify_root()
                if write:
                    try:
                        os.mkdir(directory, mode=0o750, dir_fd=root_fd)
                    except FileExistsError:
                        pass
                directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
                descriptors.append(directory_fd)
                flags = os.O_NOFOLLOW | (os.O_RDWR | os.O_CREAT | os.O_EXCL if write else os.O_RDONLY)
                fd = os.open(name, flags, mode=0o640, dir_fd=directory_fd)
                handle = os.fdopen(fd, 'w+b' if write else 'rb')
            else:
                parent = root / directory
                if write:
                    parent.mkdir(exist_ok=True)
                if parent.is_symlink() or self.is_reparse(parent) or parent.resolve().parent != root.resolve():
                    self.unavailable()
                path = parent / name
                if path.is_symlink():
                    self.unavailable()
                handle = path.open('x+b' if write else 'rb')
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                self.unavailable()
            yield handle
        except OSError:
            self.unavailable()
        finally:
            if handle:
                handle.close()
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    def remove_unbound_key(self, key):
        """仅供当前操作失败后清理其新建且尚未绑定的文件，禁止用于业务素材删除。"""
        if not re.fullmatch(r'(upload-staging|media|provider-evidence)/[a-f0-9]{32}', key):
            raise ValueError('非法内部存储键')
        directory, name = key.split('/')
        root = self.verify_root()
        if os.name != 'nt':
            root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
                try:
                    os.unlink(name, dir_fd=directory_fd)
                finally:
                    os.close(directory_fd)
            finally:
                os.close(root_fd)
        else:
            parent = root / directory
            if parent.is_symlink() or self.is_reparse(parent) or parent.resolve().parent != root.resolve():
                self.unavailable()
            (parent / name).unlink()

    def put_part(self, data):
        key = 'upload-staging/' + uuid.uuid4().hex
        with self.open_key(key, write=True) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        return key, hashlib.sha256(data).hexdigest()

    def verify_media(self, handle):
        handle.seek(0)
        header = handle.read(16)
        handle.seek(0)
        if header.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff')) or (
            header[:4] == b'RIFF' and header[8:12] == b'WEBP'
        ):
            try:
                with Image.open(handle) as picture:
                    width, height = picture.size
                    if width * height > self.policy.max_pixels or getattr(picture, 'n_frames', 1) != 1:
                        raise ValueError('图像像素超限或包含多帧')
                    mime = {'PNG': 'image/png', 'JPEG': 'image/jpeg', 'WEBP': 'image/webp'}[picture.format]
                    picture.verify()
                # verify 对部分格式不解码像素，重新打开并实际解码。
                handle.seek(0)
                with Image.open(handle) as picture:
                    picture.load()
                return {'mime_type': mime, 'width': width, 'height': height, 'seconds': None}
            except (OSError, ValueError, KeyError, Image.DecompressionBombError):
                raise ServiceWarning(
                    message='图片损坏、格式不支持或超出像素限制', data={'errorCode': 'MEDIA_INVALID'}
                ) from None
        if header[4:8] != b'ftyp' and not header.startswith(b'\x1a\x45\xdf\xa3'):
            raise ServiceWarning(
                message='仅支持经过验证的 PNG、JPEG、WebP、MP4、WebM 文件', data={'errorCode': 'MEDIA_INVALID'}
            )
        handle.seek(0)
        name = str(handle.name) if os.name == 'nt' else f'/proc/self/fd/{handle.fileno()}'
        kwargs = {} if os.name == 'nt' else {'pass_fds': (handle.fileno(),)}
        try:
            completed = subprocess.run(
                [
                    self.policy.ffprobe,
                    '-v',
                    'error',
                    '-protocol_whitelist',
                    'file,pipe',
                    '-show_entries',
                    'format=format_name,duration:stream=codec_type,width,height',
                    '-of',
                    'json',
                    name,
                ],
                capture_output=True,
                timeout=30,
                check=True,
                **kwargs,
            )
            metadata = json.loads(completed.stdout)
            video = next(stream for stream in metadata['streams'] if stream['codec_type'] == 'video')
            from decimal import Decimal

            duration = Decimal(metadata['format']['duration'])
            width, height = int(video['width']), int(video['height'])
            if (
                not duration.is_finite()
                or duration <= 0
                or width <= 0
                or height <= 0
                or width * height > self.policy.max_pixels
            ):
                raise ValueError
            formats = set(metadata['format']['format_name'].split(','))
            if 'mp4' in formats:
                mime = 'video/mp4'
            elif 'webm' in formats:
                mime = 'video/webm'
            else:
                raise ValueError
            return {'mime_type': mime, 'width': width, 'height': height, 'seconds': duration}
        except (OSError, subprocess.TimeoutExpired):
            raise ServiceWarning(
                message='视频分析工具不可用或暂时超时，请重试', data={'errorCode': 'MEDIA_VALIDATOR_UNAVAILABLE'}
            ) from None
        except (subprocess.SubprocessError, ValueError, KeyError, StopIteration):
            raise ServiceWarning(
                message='视频校验失败或媒体分析工具不可用', data={'errorCode': 'MEDIA_INVALID'}
            ) from None

    def verify_file(self, handle, declared_mime):
        """媒体默认校验；管理文档由独立存储策略覆盖。"""
        return self.verify_media(handle)

    def accepts_verified_mime(self, actual_mime, declared_mime):
        """默认要求声明格式与实际格式一致。"""
        return actual_mime == declared_mime

    def assemble(self, parts, expected_size, expected_sha256, declared_mime):
        key = 'media/' + uuid.uuid4().hex
        digest, size = hashlib.sha256(), 0
        with self.open_key(key, write=True) as output:
            for part in parts:
                part_digest, part_size = hashlib.sha256(), 0
                with self.open_key(part['storage_key']) as source:
                    while chunk := source.read(1024 * 1024):
                        size += len(chunk)
                        part_size += len(chunk)
                        if size > expected_size:
                            raise ServiceWarning(
                                message='上传文件大小不一致', data={'errorCode': 'UPLOAD_CHECKSUM_MISMATCH'}
                            )
                        digest.update(chunk)
                        part_digest.update(chunk)
                        output.write(chunk)
                if part_digest.hexdigest() != part['sha256'] or part_size != part['byte_size']:
                    raise ServiceWarning(
                        message='分片内容已损坏，请重新上传', data={'errorCode': 'UPLOAD_CHECKSUM_MISMATCH'}
                    )
            if size != expected_size or digest.hexdigest() != expected_sha256:
                raise ServiceWarning(message='文件摘要或大小不一致', data={'errorCode': 'UPLOAD_CHECKSUM_MISMATCH'})
            output.flush()
            os.fsync(output.fileno())
            metadata = self.verify_file(output, declared_mime)
            if not self.accepts_verified_mime(metadata['mime_type'], declared_mime):
                raise ServiceWarning(message='实际文件类型与声明不符', data={'errorCode': 'MEDIA_TYPE_MISMATCH'})
        return {'storage_key': key, 'sha256': digest.hexdigest(), 'byte_size': size, **metadata}
