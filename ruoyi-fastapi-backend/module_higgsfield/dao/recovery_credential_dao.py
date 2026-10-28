"""仅供本地恢复核验读取加密字段，不用于HTTP接口。"""

from sqlalchemy import select
from module_higgsfield.entity.do.credential_do import HfCredentialVersion as Version


class RecoveryCredentialDao:
    @staticmethod
    async def page(db, after_id, limit):
        rows = await db.execute(select(
            Version.credential_version_id, Version.credential_id, Version.connection_version_id,
            Version.version_no, Version.secret_ciphertext, Version.nonce, Version.auth_tag,
            Version.master_key_version, Version.fingerprint, Version.masked_suffix,
        ).where(Version.credential_version_id > after_id)
          .order_by(Version.credential_version_id).limit(limit))
        return [dict(row) for row in rows.mappings()]
