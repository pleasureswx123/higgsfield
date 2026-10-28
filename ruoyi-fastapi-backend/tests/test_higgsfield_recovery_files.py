"""恢复文件核验：真实临时文件、只读分页边界和脱敏报告。"""

import hashlib
import importlib.util
import os
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch
from sqlalchemy import text
from tests import test_higgsfield_output_read as reads

from module_higgsfield.service.recovery_file_service import RecoveryFileService
from module_higgsfield.service.storage_service import StoragePolicy, StorageService


class RecoveryFileTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / 'media').mkdir()
        self.storage = StorageService(StoragePolicy(str(self.root), 'local-test', '', 1000, 1000))
        self.row = dict(file_id=9007199254740993, storage_key='media/' + 'a' * 32,
                        sha256=hashlib.sha256(b'abc').hexdigest(), byte_size=3, state='1')
        self.path = self.root / self.row['storage_key']
        self.path.write_bytes(b'abc')

    def test_integrity_and_mismatch_without_mutation(self):
        self.assertEqual(RecoveryFileService.check(self.storage, self.row), 'verified')
        self.path.write_bytes(b'abd')
        self.assertEqual(RecoveryFileService.check(self.storage, self.row), 'hash_mismatch')
        self.path.write_bytes(b'abcd')
        self.assertEqual(RecoveryFileService.check(self.storage, self.row), 'size_mismatch')
        self.assertEqual(self.path.read_bytes(), b'abcd')
        self.path.unlink()
        self.assertEqual(RecoveryFileService.check(self.storage, self.row), 'unreadable')
        self.assertFalse(self.path.exists())

    def test_invalid_key_metadata_and_purged_records(self):
        self.assertEqual(RecoveryFileService.check(self.storage, self.row | {'storage_key': '../secret'}), 'invalid_storage_key')
        self.assertEqual(RecoveryFileService.check(self.storage, self.row | {'sha256': 'bad'}), 'invalid_metadata')
        self.path.unlink()
        self.assertEqual(RecoveryFileService.check(self.storage, self.row | {'state': '4'}), 'purged_skipped')

    async def test_pagination_closes_session_before_file_read_and_caps_samples(self):
        active = False
        db = AsyncMock()

        @asynccontextmanager
        async def sessions():
            nonlocal active
            active = True
            try:
                yield db
            finally:
                active = False

        original = RecoveryFileService.check

        def check(storage, row):
            self.assertFalse(active)
            return original(storage, row)

        rows = [self.row, self.row | {'file_id': self.row['file_id'] + 1, 'sha256': 'b' * 64},
                self.row | {'file_id': self.row['file_id'] + 2, 'byte_size': 8}]
        with patch('module_higgsfield.service.recovery_file_service.RecoveryFileDao.page',
                   AsyncMock(side_effect=[rows[:2], rows[2:], [], [], []])) as page, \
                patch.object(RecoveryFileService, 'check', side_effect=check):
            report = await RecoveryFileService.audit(sessions, self.storage, page_size=2, sample_limit=1)
        self.assertEqual([call.args[1] for call in page.call_args_list], [0, rows[1]['file_id'], rows[2]['file_id'], 0, 0])
        self.assertEqual(report['total'], 3)
        self.assertEqual(report['failed'], 2)
        self.assertEqual(report['failures'], [{'source': 'stored_file', 'recordId': str(rows[1]['file_id']), 'reason': 'hash_mismatch'}])
        self.assertTrue(report['failuresTruncated'])
        self.assertFalse(report['fullRecoveryVerified'])
        self.assertNotIn(str(self.root), str(report))
        self.assertNotIn('storage_key', str(report))
        self.assertTrue(all(str(call.args[0]) == 'SET TRANSACTION READ ONLY' for call in db.execute.call_args_list))
        self.assertEqual(self.path.read_bytes(), b'abc')

    async def test_database_failure_does_not_produce_success_report(self):
        @asynccontextmanager
        async def sessions():
            yield AsyncMock()

        with patch('module_higgsfield.service.recovery_file_service.RecoveryFileDao.page',
                   AsyncMock(side_effect=RuntimeError('private-db-detail'))):
            with self.assertRaises(RuntimeError):
                await RecoveryFileService.audit(sessions, self.storage)

    async def test_invalid_limits_fail_before_storage_access(self):
        with patch.object(self.storage, 'verify_root') as verify:
            with self.assertRaises(ValueError):
                await RecoveryFileService.audit(None, self.storage, page_size=0)
            verify.assert_not_called()


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class RecoveryFileDatabaseTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = reads.OutputReadTests.cleanup_schema
    migrate = reads.OutputReadTests.migrate
    job = reads.OutputReadTests.job
    output = reads.OutputReadTests.output
    create = reads.OutputReadTests.create
    async def asyncSetUp(self):
        await reads.OutputReadTests.asyncSetUp(self)
        for table, filename in (
            ('hf_provider_response', '20261027_37_provider_responses.py'),
            ('hf_credential_test_response', '20261028_59_credential_test_responses.py'),
        ):
            async with self.sessions() as db:
                exists = await db.scalar(text('SELECT to_regclass(:name)'), {'name': table})
            if exists is None:
                spec = importlib.util.spec_from_file_location(
                    'recovery_setup', Path(__file__).resolve().parents[1] / 'alembic/versions' / filename)
                self.migration = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(self.migration)
                await self.migrate('upgrade')

    async def test_real_inventory_is_read_only_and_detects_changed_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'media').mkdir()
            storage = StorageService(StoragePolicy(str(root), 'local-test', '', 1000, 1000))
            async with self.sessions() as db:
                ids = list(await db.scalars(text('SELECT file_id FROM hf_stored_file ORDER BY file_id')))
                self.assertTrue(ids)
                for identity in ids:
                    key = f'media/{identity:032x}'
                    (root / key).write_bytes(b'restored')
                    await db.execute(text(
                        "UPDATE hf_stored_file SET storage_key=:key,sha256=:digest,byte_size=8,state='1' WHERE file_id=:id"
                    ), {'key': key, 'digest': hashlib.sha256(b'restored').hexdigest(), 'id': identity})
                await db.commit()
            report = await RecoveryFileService.audit(self.sessions, storage, page_size=1)
            self.assertEqual(report['counts'], {'verified': len(ids)})
            (root / f'media/{ids[0]:032x}').write_bytes(b'corrupt!')
            report = await RecoveryFileService.audit(self.sessions, storage, page_size=1)
            self.assertEqual(report['failed'], 1)
            self.assertEqual(report['failures'][0], {'source': 'stored_file', 'recordId': str(ids[0]), 'reason': 'hash_mismatch'})
            async with self.sessions() as db:
                states = list(await db.scalars(text('SELECT state FROM hf_stored_file')))
                self.assertEqual(states, ['1'] * len(ids))
            # 两类证据编号可相同，报告必须通过来源区分；无需解密即可发现损坏。
            (root / 'provider-evidence').mkdir()
            digest = hashlib.sha256(b'ciphertext').hexdigest()
            async with self.sessions() as db:
                for index, (table, owner_column) in enumerate((
                    ('hf_provider_response', 'job_id'),
                    ('hf_credential_test_response', 'test_id'),
                ), start=1):
                    key = 'provider-evidence/' + str(index) * 32
                    (root / key).write_bytes(b'ciphertext')
                    # 表名与列名均为固定测试白名单，不来自外部输入。
                    await db.execute(text(
                        f'INSERT INTO {table}(provider_call_id,{owner_column},storage_key,sha256,byte_size,http_status,create_time,update_time) '
                        'VALUES(1,1,:key,:digest,10,200,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)'
                    ), {'key': key, 'digest': digest})
                await db.commit()
            report = await RecoveryFileService.audit(self.sessions, storage, page_size=1)
            for source in ('provider_response', 'credential_test_response'):
                self.assertEqual(report['sources'][source], {'verified': 1})
            (root / ('provider-evidence/' + '1' * 32)).write_bytes(b'corrupted!')
            (root / ('provider-evidence/' + '2' * 32)).unlink()
            report = await RecoveryFileService.audit(self.sessions, storage, page_size=1)
            self.assertEqual(report['failed'], 3)
            self.assertEqual(report['sources']['provider_response'], {'hash_mismatch': 1})
            self.assertEqual(report['sources']['credential_test_response'], {'unreadable': 1})
            self.assertEqual({row['source'] for row in report['failures']},
                             {'stored_file', 'provider_response', 'credential_test_response'})
            self.assertNotIn('ciphertext', str(report))

    async def test_response_authentication_checks_keys_context_and_domain(self):
        from module_higgsfield.service.credential_crypto_service import CredentialKeyring
        from module_higgsfield.service.provider_response_crypto_service import ProviderResponseCryptoService
        from module_higgsfield.service.credential_test_response_crypto_service import CredentialTestResponseCryptoService
        from module_higgsfield.service.provider_response_storage_service import ProviderResponseStorageService
        from module_higgsfield.service.recovery_evidence_service import RecoveryEvidenceService

        keyring = CredentialKeyring('restore', {'restore': b'a' * 32}, b'b' * 32)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage = StorageService(StoragePolicy(str(root), 'local-test', '', 1000, 1000))
            facts = []
            async with self.sessions() as db:
                for table, owner, crypto in (
                    ('hf_provider_response', 'job_id', ProviderResponseCryptoService(keyring)),
                    ('hf_credential_test_response', 'test_id', CredentialTestResponseCryptoService(keyring)),
                ):
                    reader = ProviderResponseStorageService(storage, crypto, max_bytes=1000)
                    file = await reader.save({'private': 'restore-private-body'}, 1, 1)
                    facts.append(file)
                    await db.execute(text(
                        f'INSERT INTO {table}(provider_call_id,{owner},storage_key,sha256,byte_size,http_status,create_time,update_time) '
                        'VALUES(1,1,:storage_key,:sha256,:byte_size,200,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)'
                    ), file)
                await db.commit()
            report = await RecoveryEvidenceService.audit(self.sessions, storage, keyring, page_size=1)
            self.assertEqual(report['counts'], {'verified': 2})
            missing = CredentialKeyring('new', {'new': b'c' * 32}, b'b' * 32)
            self.assertEqual((await RecoveryEvidenceService.audit(self.sessions, storage, missing))['failed'], 2)
            async with self.sessions() as db:
                await db.execute(text('UPDATE hf_credential_test_response SET test_id=2'))
                await db.commit()
            report = await RecoveryEvidenceService.audit(self.sessions, storage, keyring)
            self.assertEqual(report['failed'], 1)
            self.assertEqual(report['failures'][0]['source'], 'credential_test_response')
            # 替换为另一域的完整密文并同步摘要，仍必须认证失败。
            provider_bytes = (root / facts[0]['storage_key']).read_bytes()
            (root / facts[1]['storage_key']).write_bytes(provider_bytes)
            async with self.sessions() as db:
                await db.execute(text('UPDATE hf_credential_test_response SET test_id=1,sha256=:digest,byte_size=:size'),
                                 {'digest': hashlib.sha256(provider_bytes).hexdigest(), 'size': len(provider_bytes)})
                await db.commit()
            report = await RecoveryEvidenceService.audit(self.sessions, storage, keyring, sample_limit=0)
            self.assertEqual(report['failed'], 1)
            self.assertEqual(report['failures'], [])
            self.assertTrue(report['failuresTruncated'])
            self.assertNotIn('restore-private-body', str(report))
            self.assertNotIn('storage_key', str(report))
            self.assertEqual((root / facts[1]['storage_key']).read_bytes(), provider_bytes)
