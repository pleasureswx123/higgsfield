"""项目上传同时支持媒体和元素模板，按声明用途对应的格式实际校验。"""
from module_higgsfield.service.storage_service import StorageService
from module_higgsfield.service.document_storage_service import DocumentStorageService
from module_higgsfield.entity.vo.asset_formats import DOCUMENT_MIME_TYPES


class ProjectUploadStorageService(StorageService):
    document_types = set(DOCUMENT_MIME_TYPES.values()) | {'text/csv',
                      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}

    def verify_file(self, handle, declared_mime):
        if declared_mime in self.document_types:
            return DocumentStorageService(self.policy).verify_file(handle, declared_mime)
        return super().verify_file(handle, declared_mime)
