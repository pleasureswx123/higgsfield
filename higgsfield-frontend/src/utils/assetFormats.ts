export const documentFormats = {
  pdf: 'application/pdf', txt: 'text/plain', md: 'text/markdown', html: 'text/html',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
} as const
export type AssetFileType = 'image' | 'video' | keyof typeof documentFormats
export const assetAccept = 'image/png,image/jpeg,image/webp,video/mp4,video/webm,.pdf,.txt,.md,.html,.docx,.pptx'
export function assetUploadMime(file: Pick<File, 'name' | 'type'>): string {
  const suffix = file.name.split('.').pop()?.toLowerCase() || ''
  // 扩展名只用于浏览器MIME兼容；实际内容仍由服务端校验。
  if (suffix in documentFormats) return documentFormats[suffix as keyof typeof documentFormats]
  return ['image/png', 'image/jpeg', 'image/webp', 'video/mp4', 'video/webm'].includes(file.type) ? file.type : ''
}
export function assetExtension(mime: string): string {
  const formats: Record<string, string> = { 'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp', 'video/mp4': 'mp4', 'video/webm': 'webm' }
  for (const [extension, value] of Object.entries(documentFormats)) formats[value] = extension
  return formats[mime] ? '.' + formats[mime] : ''
}
