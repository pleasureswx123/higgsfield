"""复用认证加密封装，临时上传使用独立域并绑定上传ID及原凭据。"""

from module_higgsfield.service.output_source_crypto_service import OutputSourceCryptoService

MAX_ID = 9223372036854775807


class ProviderUploadCryptoService(OutputSourceCryptoService):
    @staticmethod
    def context(provider_upload_id: int, credential_version_id: int) -> bytes:
        if any(
            type(value) is not int or not 1 <= value <= MAX_ID for value in (provider_upload_id, credential_version_id)
        ):
            raise ValueError('临时上传加密身份无效')
        return f'hf:provider-upload-url:v1:{provider_upload_id}:{credential_version_id}'.encode('ascii')
