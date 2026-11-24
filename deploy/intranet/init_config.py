"""在全新服务器上生成独立生产密钥，只写 root 可读的配置目录。"""
import base64
import json
import os
from pathlib import Path
import secrets
import subprocess

root = Path('/etc/higgsfield')
os.umask(0o077)
if any((root / name).exists() for name in ('db.env', 'app.env')):
    raise SystemExit('生产配置已存在，不能覆盖')

password = secrets.token_urlsafe(36)
rsa = subprocess.check_output(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:3072'],
                              stderr=subprocess.DEVNULL)
public = subprocess.check_output(['openssl', 'pkey', '-pubout'], input=rsa)

def pem(data):
    return data.decode().strip().replace('\n', r'\n')

def key():
    return base64.b64encode(secrets.token_bytes(32)).decode()

def write_env(name, values):
    (root / name).write_text(''.join(f"{k}='{v}'\n" for k, v in values.items()), encoding='utf-8')

write_env('db.env', {'POSTGRES_USER': 'higgsfield', 'POSTGRES_DB': 'higgsfield_prod', 'POSTGRES_PASSWORD': password})
write_env('app.env', {
    'APP_ENV': 'prod', 'APP_NAME': 'Nightmare Theatre', 'APP_ROOT_PATH': '', 'APP_PORT': 9099,
    'APP_RELOAD': 'false', 'APP_WORKERS': 1, 'APP_DISABLE_SWAGGER': 'true', 'APP_DISABLE_REDOC': 'true',
    'APP_DEFAULT_ENABLED_PLUGINS': '', 'APP_IP_LOCATION_QUERY': 'false',
    'JWT_SECRET_KEY': secrets.token_hex(48), 'REDIS_HOST': 'redis', 'REDIS_PORT': 6379,
    'DB_DEFAULT_SOURCE': 'primary', 'DB_SOURCES': json.dumps({'primary': {
        'db_type': 'postgresql', 'db_host': 'postgres', 'db_port': 5432, 'db_username': 'higgsfield',
        'db_password': password, 'db_database': 'higgsfield_prod', 'db_echo': False,
        'db_pool_size': 4, 'db_max_overflow': 4}}),
    'TRANSPORT_CRYPTO_ENABLED': 'true', 'TRANSPORT_CRYPTO_MODE': 'optional',
    'TRANSPORT_CRYPTO_KID': 'prod-1', 'TRANSPORT_CRYPTO_RSA_KEY_SIZE': 3072,
    'TRANSPORT_CRYPTO_PUBLIC_KEY': pem(public), 'TRANSPORT_CRYPTO_PRIVATE_KEY': pem(rsa),
    'HF_CREDENTIAL_MASTER_KEYS': json.dumps({'prod-1': key()}), 'HF_CREDENTIAL_ACTIVE_KEY_VERSION': 'prod-1',
    'HF_CREDENTIAL_FINGERPRINT_KEY': key(), 'HF_ESTIMATE_TOKEN_KEY': key(),
    'HF_STORAGE_MODE': 'nas', 'HF_STORAGE_ROOT': '/nas/prod/.platform',
    'HF_NAS_SOURCE': '//192.168.1.13/Project', 'HF_NAS_PROJECT_DIRECTORIES': 1,
    'HF_UPLOAD_MAX_BYTES': 67108864, 'HF_IMAGE_MAX_PIXELS': 40000000, 'HF_IMAGE_MAX_DECODED_BYTES': 33554432,
})
