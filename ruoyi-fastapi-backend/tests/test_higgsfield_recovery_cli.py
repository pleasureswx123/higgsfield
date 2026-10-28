"""恢复命令真实子进程验证；数据库连接限定在本测试独有schema。"""

import asyncio
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from sqlalchemy import text
from module_higgsfield.dao.recovery_sequence_dao import RecoverySequenceDao
from tests import test_higgsfield_recovery_files as files

ROOT = Path(__file__).resolve().parents[1]


class RecoveryCliArgumentTests(unittest.TestCase):
    def test_invalid_ranges_and_unconfirmed_run_exit_before_configuration(self):
        for args in ([], ['--confirm-quiesced', '--page-size', '0'],
                     ['--confirm-quiesced', '--sample-limit', '1001']):
            result = subprocess.run([sys.executable, '-m', 'module_higgsfield.recovery_check', *args],
                                    cwd=ROOT, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, b'')


@unittest.skipUnless(os.getenv('HF_RUN_DB_TESTS') == '1', '需要显式启用隔离数据库测试')
class RecoveryCliDatabaseTests(unittest.IsolatedAsyncioTestCase):
    cleanup_schema = files.RecoveryFileDatabaseTests.cleanup_schema
    migrate = files.RecoveryFileDatabaseTests.migrate
    job = files.RecoveryFileDatabaseTests.job
    output = files.RecoveryFileDatabaseTests.output
    create = files.RecoveryFileDatabaseTests.create

    async def asyncSetUp(self):
        await files.RecoveryFileDatabaseTests.asyncSetUp(self)
        for filename in ('20261027_07_elements.py', '20261027_17_credentials.py', '20261027_27_budgets.py',
                         '20261027_26_exchange_rates.py', '20261027_39_billing_facts.py', '20261028_76_media_derivatives.py'):
            spec = importlib.util.spec_from_file_location('cli_setup', ROOT / 'alembic/versions' / filename)
            self.migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.migration)
            await self.migrate('upgrade')

    async def test_real_command_aggregates_and_never_prints_partial_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'media').mkdir()
            async with self.sessions() as db:
                ids = list(await db.scalars(text('SELECT file_id FROM hf_stored_file')))
                for identity in ids:
                    key = f'media/{identity:032x}'
                    (root / key).write_bytes(b'cli-test')
                    await db.execute(text('UPDATE hf_stored_file SET storage_key=:key,sha256=:digest,byte_size=8 WHERE file_id=:id'),
                                     {'key': key, 'digest': hashlib.sha256(b'cli-test').hexdigest(), 'id': identity})
                # 部分迁移夹具显式插入ID；仅调整本测试schema，构造已恢复序列的基线。
                for row in await RecoverySequenceDao.inventory(db):
                    if row['sequence_name'] and row['max_id'] is not None:
                        quote = db.bind.dialect.identifier_preparer.quote_identifier
                        name = f"{quote(row['sequence_schema'])}.{quote(row['sequence_name'])}"
                        await db.execute(text('SELECT setval(CAST(:name AS regclass),:value,true)'),
                                         {'name': name, 'value': row['max_id']})
                await db.commit()
            env = {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'APP_ENV': 'test',
                   'HF_RECOVERY_TEST_SCHEMA': self.schema, 'HF_STORAGE_ROOT': str(root),
                   'HF_STORAGE_MODE': 'local-test', 'HF_UPLOAD_MAX_BYTES': '1000', 'HF_IMAGE_MAX_PIXELS': '1000',
                   'HF_CREDENTIAL_ACTIVE_KEY_VERSION': 'test',
                   'HF_CREDENTIAL_MASTER_KEYS': json.dumps({'test': base64.b64encode(b'a' * 32).decode()}),
                   'HF_CREDENTIAL_FINGERPRINT_KEY': base64.b64encode(b'b' * 32).decode()}
            # 复用真实框架配置和命令main，仅替换引擎工厂以限定独有schema；不模拟任何核验服务。
            bridge = '''
import os
import config.database as database
from sqlalchemy.ext.asyncio import create_async_engine
schema = os.environ['HF_RECOVERY_TEST_SCHEMA']
assert schema.startswith('hf_project_test_') and schema.replace('_', '').isalnum()
def factory(**kwargs):
    engine = create_async_engine(database.build_async_sqlalchemy_database_url(), echo=False,
        connect_args={'server_settings': {'search_path': schema}})
    if os.environ.get('HF_RECOVERY_TEST_DISPOSE_FAILURE') == '1':
        original = type(engine).dispose
        async def fail_dispose(instance):
            await original(instance)
            raise RuntimeError('private-cleanup-detail')
        # 只在此测试子进程注入清理故障，会话与核验仍使用真实引擎。
        type(engine).dispose = fail_dispose
    return engine
database.create_async_db_engine = factory
from module_higgsfield.recovery_check import main
raise SystemExit(main())
'''

            async def invoke():
                return await asyncio.to_thread(subprocess.run,
                    [sys.executable, '-c', bridge, '--env', 'test', '--confirm-quiesced'],
                    cwd=ROOT, env=env, capture_output=True, encoding='utf-8', timeout=30)

            success = await invoke()
            self.assertEqual(success.returncode, 0, success.stderr)
            report = json.loads(success.stdout)
            self.assertEqual(report['failed'], 0)
            self.assertEqual(report['files']['total'], len(ids))
            self.assertEqual(report['references']['rulesChecked'], 21)
            self.assertGreater(report['sequences']['total'], 1)
            self.assertEqual(report['credentials']['total'], 0)
            self.assertEqual(report['evidence']['total'], 0)
            self.assertEqual(report['budgets']['total'], 0)
            self.assertFalse(report['fullRecoveryVerified'])
            (root / f'media/{ids[0]:032x}').write_bytes(b'bad-data')
            failure = await invoke()
            self.assertEqual(failure.returncode, 2, failure.stderr)
            self.assertEqual(json.loads(failure.stdout)['files']['failed'], 1)
            env['HF_RECOVERY_TEST_DISPOSE_FAILURE'] = '1'
            cleanup_failure = await invoke()
            self.assertEqual(cleanup_failure.returncode, 3)
            self.assertEqual(cleanup_failure.stdout, '')
            self.assertIn('RuntimeError', cleanup_failure.stderr)
            self.assertNotIn('private-cleanup-detail', cleanup_failure.stderr)
            del env['HF_RECOVERY_TEST_DISPOSE_FAILURE']
            async with self.sessions() as db:
                await db.execute(text('ALTER TABLE hf_credential_version RENAME TO hf_credential_version_unavailable'))
                await db.commit()
            interrupted = await invoke()
            self.assertEqual(interrupted.returncode, 3)
            self.assertEqual(interrupted.stdout, '')
            self.assertIn('恢复核验未完成', interrupted.stderr)
            self.assertNotIn('SELECT', interrupted.stderr)
