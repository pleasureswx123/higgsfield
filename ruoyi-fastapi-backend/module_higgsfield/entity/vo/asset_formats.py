"""素材文档格式白名单，上传校验、绑定及筛选共用。"""
DOCUMENT_MIME_TYPES = {
    'pdf': 'application/pdf',
    'txt': 'text/plain',
    'md': 'text/markdown',
    'html': 'text/html',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
}
MEDIA_MIME_TYPES = {'image/png', 'image/jpeg', 'image/webp', 'video/mp4', 'video/webm'}


def asset_media_type(mime):
    if mime in DOCUMENT_MIME_TYPES.values():
        return 'document'
    if mime in MEDIA_MIME_TYPES:
        return mime.split('/')[0]
    return None
