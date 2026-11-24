"""验证项目归档名、层级变更、冲突和断点重试。"""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from module_higgsfield.service.nas_directory_service import NasDirectoryService


class NasDirectoriesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        from unittest.mock import patch
        self.enterContext(patch.dict('os.environ', {'APP_ENV': 'dev'}))
        self.root = Path(temp.name) / 'dev'
        objects = self.root / '.platform'
        (objects / 'media').mkdir(parents=True)
        storage = SimpleNamespace(verify_root=lambda: objects, policy=SimpleNamespace(mode='nas'))
        self.service = NasDirectoryService(storage)
        self.key = 'media/' + 'a' * 32
        self.source = objects / self.key
        self.source.write_bytes(b'123')
        self.rows = [
            self.row('project', 1, '剧组'), self.row('folder', 2, '第一集'),
            self.row('folder', 3, '镜头', 2), self.row('asset', 4, '定妆照.jpg', 3),
        ]

    def row(self, kind, identity, name, parent=None):
        return dict(kind=kind, id=identity, project_id=1, parent=parent, name=name,
                    storage_key=self.key if kind == 'asset' else None, mime_type='image/png')

    def test_move_rename_delete_preserve_bytes_and_unmanaged_files(self):
        self.service.sync(self.rows)
        old = self.root / '剧组/第一集/镜头/定妆照.png'
        self.assertTrue(old.samefile(self.source))
        extra = old.with_name('制作笔记.txt')
        extra.write_text('保留', encoding='utf-8')
        self.rows[0]['name'] = '新项目名'
        self.rows[2].update(name='镜头二', parent=None)
        self.service.sync(self.rows)
        self.assertFalse(old.exists())
        self.assertEqual(extra.read_text('utf-8'), '保留')
        new = self.root / '剧组/镜头二/定妆照.png'
        self.assertTrue(new.samefile(self.source))
        self.service.sync(self.rows[:2])
        self.assertFalse(new.parent.exists())
        self.assertTrue(self.source.exists())
        self.assertTrue((self.root / '剧组/第一集').is_dir())

    def test_collision_and_retry_after_missing_source(self):
        self.rows.append(self.row('asset', 5, '定妆照.png', 3))
        self.source.unlink()
        with self.assertRaises(FileNotFoundError):
            self.service.sync(self.rows)
        self.source.write_bytes(b'abc')
        self.service.sync(self.rows)
        files = list((self.root / '剧组/第一集/镜头').iterdir())
        self.assertEqual({p.name for p in files}, {'定妆照.png', '定妆照（2）.png'})
        self.assertTrue(all(p.samefile(self.source) for p in files))
        self.service.sync(self.rows)
        self.assertEqual(len(list(files[0].parent.iterdir())), 2)

    def test_windows_names_and_existing_directory(self):
        (self.root / '剧组').mkdir()
        self.rows[1]['name'] = '../CON:第一集'
        self.service.sync(self.rows)
        self.assertEqual(list((self.root / '剧组').iterdir()), [])
        manifest = json.loads((self.root / '.platform/directory.json').read_text('utf-8'))
        self.assertTrue(manifest['entries']['folder-2']['path'].startswith('剧组（2）/'))
        self.assertEqual(len(list((self.root / '剧组（2）').glob('*/*/*.png'))), 1)


    def test_external_replacement_is_preserved(self):
        self.service.sync(self.rows)
        target = self.root / '剧组/第一集/镜头/定妆照.png'
        target.unlink()
        target.write_bytes(b'external')
        self.service.sync(self.rows)
        self.assertEqual(target.read_bytes(), b'external')
        self.assertTrue(target.with_name('定妆照（2）.png').samefile(self.source))

    def test_folder_move_with_explorer_thumbnail_cache(self):
        self.service.sync(self.rows)
        old = self.root / '剧组/第一集/镜头'
        (old / 'Thumbs.db').write_bytes(b'cache')
        self.rows[2]['parent'] = None
        self.service.sync(self.rows)
        self.assertFalse(old.exists())
        self.assertTrue((self.root / '剧组/镜头/定妆照.png').samefile(self.source))
        archived = list((self.root / '.platform/retired-thumbnail-caches').glob('*/Thumbs.db'))
        self.assertEqual([item.read_bytes() for item in archived], [b'cache'])
