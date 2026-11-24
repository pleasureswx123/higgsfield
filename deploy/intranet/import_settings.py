"""首次发布导入管理配置。只允许经 SSH 转发到尚未创建项目的全新正式库。"""
import base64
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import secrets
import subprocess

import bcrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from dotenv import dotenv_values
import psycopg2
from psycopg2.extras import DictCursor, Json, execute_values

HOST = 'root@192.168.1.100'
ROOT = Path(__file__).resolve().parents[2]
SOURCE_ENV = dotenv_values(ROOT / 'ruoyi-fastapi-backend/.env.dev')
TARGET_ENV = dotenv_values(stream=io.StringIO(subprocess.check_output(
    ['ssh', '-o', 'BatchMode=yes', HOST, 'cat /etc/higgsfield/app.env']).decode()))
TABLES = {
    'sys_dept': '', 'sys_post': '', 'sys_dict_type': '', 'sys_dict_data': '', 'sys_menu': '',
    'sys_config': '', 'sys_role': '', 'sys_role_menu': '', 'sys_role_dept': '',
    'sys_user': "WHERE del_flag='0' AND (user_name !~ '^(hf_test_|qa_)' OR user_id IN (SELECT owner_id FROM hf_provider_credential))",
    'sys_identity_subject': "WHERE user_id IN (SELECT user_id FROM sys_user WHERE del_flag='0' AND (user_name !~ '^(hf_test_|qa_)' OR user_id IN (SELECT owner_id FROM hf_provider_credential)))",
    'sys_user_role': "WHERE user_id IN (SELECT user_id FROM sys_user WHERE del_flag='0' AND user_name !~ '^(hf_test_|qa_)')",
    'sys_user_post': "WHERE user_id IN (SELECT user_id FROM sys_user WHERE del_flag='0' AND user_name !~ '^(hf_test_|qa_)')",
    'hf_project_role': '', 'hf_project_role_permission': '', 'hf_cost_center': '',
    'hf_provider_connection': '', 'hf_provider_connection_version': '', 'hf_provider_account': '',
    'hf_model_profile': '', 'hf_model_profile_version': '', 'hf_model_variant': '',
    'hf_provider_credential': '', 'hf_credential_version': '', 'hf_price_book': '',
    'hf_price_source': '', 'hf_price_version': '', 'hf_price_rule_item': '', 'hf_price_version_source': '',
    'hf_price_activation': '', 'hf_price_publish_event': '', 'hf_exchange_rate_version': '',
    'hf_project_routing_set': 'WHERE project_id IS NULL', 'hf_project_provider_config': 'WHERE project_id IS NULL',
    'hf_routing_policy': 'WHERE project_provider_config_id IN (SELECT config_id FROM hf_project_provider_config WHERE project_id IS NULL)',
}

def connect(config, expected, port=None):
    source = json.loads(config['DB_SOURCES'])['primary']
    if source['db_database'] != expected:
        raise RuntimeError('数据库名称与部署目标不匹配')
    return psycopg2.connect(host='127.0.0.1', port=port or source['db_port'], user=source['db_username'],
                            password=source['db_password'], dbname=expected, connect_timeout=8)

def rekey(row):
    old = json.loads(SOURCE_ENV['HF_CREDENTIAL_MASTER_KEYS'])[row['master_key_version']]
    ver = TARGET_ENV['HF_CREDENTIAL_ACTIVE_KEY_VERSION']
    new = base64.b64decode(json.loads(TARGET_ENV['HF_CREDENTIAL_MASTER_KEYS'])[ver])
    ctx = 'hf:credential:v1:{credential_id}:{connection_version_id}:{version_no}'.format(**row).encode()
    secret = AESGCM(base64.b64decode(old)).decrypt(bytes(row['nonce']), bytes(row['secret_ciphertext']) + bytes(row['auth_tag']), ctx)
    row['nonce'] = os.urandom(12)
    cipher = AESGCM(new).encrypt(row['nonce'], secret, ctx)
    if AESGCM(new).decrypt(row['nonce'], cipher, ctx) != secret:
        raise RuntimeError('生产密钥回读失败')
    row.update(secret_ciphertext=cipher[:-16], auth_tag=cipher[-16:], master_key_version=ver,
               fingerprint=hmac.new(base64.b64decode(TARGET_ENV['HF_CREDENTIAL_FINGERPRINT_KEY']),
                                    b'hf:credential:fingerprint:v1:' + secret, hashlib.sha256).hexdigest())

def main():
    with connect(SOURCE_ENV, 'higgsfield_ai_dev') as source, connect(TARGET_ENV, 'higgsfield_prod', 49174) as target:
        source.set_session(readonly=True, isolation_level='REPEATABLE READ')
        with source.cursor(cursor_factory=DictCursor) as src, target.cursor() as dst:
            dst.execute("SELECT version_num FROM alembic_version")
            if dst.fetchone() != ('20261109_91',):
                raise RuntimeError('目标版本不匹配')
            dst.execute('SELECT (SELECT count(*) FROM hf_project), (SELECT count(*) FROM hf_provider_connection), (SELECT count(*) FROM hf_creation_job)')
            if dst.fetchone() != (0, 0, 0):
                raise RuntimeError('仅支持首次导入全新正式库')
            src.execute('SELECT count(*) FROM hf_price_source WHERE file_id IS NOT NULL')
            if src.fetchone()[0]:
                raise RuntimeError('价格依据包含文件，须先迁移对应附件')
            admin_password = secrets.token_urlsafe(22) + 'A7!'
            admin_hash = bcrypt.hashpw(admin_password.encode(), bcrypt.gensalt()).decode()
            default_password = secrets.token_urlsafe(20) + 'A7!'
            initial_passwords = {}
            dst.execute('DELETE FROM sys_identity_subject')
            for table, where in TABLES.items():
                src.execute(f'SELECT * FROM {table} {where}')
                columns = [col.name for col in src.description]
                records = [dict(row) for row in src.fetchall()]
                dst.execute(f'SELECT * FROM {table} LIMIT 0')
                if set(columns) != {c.name for c in dst.description}:
                    raise RuntimeError(f'{table} 的源和目标列不同，需要核对迁移')
                # 目标尚未服务用户，只替换初始化 SQL 与迁移写入的预置配置。
                dst.execute(f'DELETE FROM {table}')
                for row in records:
                    if table == 'hf_credential_version':
                        rekey(row)
                    if table == 'sys_user':
                        if row['user_name'] == 'admin':
                            row['password'] = admin_hash
                        elif row['user_name'].startswith(('hf_test_', 'qa_')):
                            row['status'] = '1'
                            row['password'] = bcrypt.hashpw(secrets.token_bytes(32), bcrypt.gensalt()).decode()
                        elif bcrypt.checkpw(b'admin123', row['password'].encode()) or bcrypt.checkpw(b'123456', row['password'].encode()):
                            password = secrets.token_urlsafe(22) + 'A7!'
                            initial_passwords[row['user_name']] = password
                            row['password'] = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
                        row.update(login_ip='', login_date=None)
                    if table == 'sys_config' and row['config_key'] == 'sys.user.initPassword':
                        row['config_value'] = default_password
                if records:
                    vals = [[Json(row[c]) if isinstance(row[c], (list, dict)) else row[c] for c in columns] for row in records]
                    execute_values(dst, f'INSERT INTO {table} ({",".join(columns)}) VALUES %s', vals)
                dst.execute(f'SELECT count(*) FROM {table}')
                assert dst.fetchone()[0] == len(records)
                for col in columns:
                    if not col.endswith('_id'):
                        continue
                    dst.execute('SELECT pg_get_serial_sequence(%s,%s)', (table,col))
                    seq = dst.fetchone()[0]
                    if seq and records:
                        dst.execute(f"SELECT setval(%s, greatest((SELECT max({col}) FROM {table}),(SELECT last_value FROM {seq})), true)", (seq,))
                print(f'{table}: {len(records)}', flush=True)
            # 密码只通过 SSH 标准输入送到服务器，禁止写入发布目录和验收日志。
            subprocess.run(['ssh', HOST, 'umask 077; cat >/etc/higgsfield/admin-initial'],input=admin_password.encode(),check=True)
            subprocess.run(['ssh', HOST, 'umask 077; cat >/etc/higgsfield/employee-initial.json'],
                           input=json.dumps(initial_passwords).encode(),check=True)

if __name__ == '__main__':
    main()
