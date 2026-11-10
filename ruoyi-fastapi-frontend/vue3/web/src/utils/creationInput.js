const roles = { reference_image: '参考图片', reference_person: '人物参考', reference_video: '参考视频', reference_audio: '参考音频', first_frame: '首帧', last_frame: '尾帧' }
const labels = { aspect_ratio: '画面比例', aspectRatio: '画面比例', ratio: '画面比例', resolution: '分辨率', quality: '质量', duration: '时长', duration_seconds: '时长', size: '尺寸', count: '数量', n: '数量', num_images: '数量', batch_size: '数量', mode: '模式', generation_mode: '模式', bitrate_mode: '码率', seed: '随机种子', audio: '生成音频', generate_audio: '生成音频' }

// 只读取已保存输入，不执行富文本 HTML，也不以当前默认参数补齐历史数据。
export function creationInput(task) {
  const input = task?.input || {}
  const references = (Array.isArray(input.references) ? input.references : []).map((item, index) => ({
    key: String(item.referenceKey),
    name: task?.referenceNames?.[item.assetVersionId] || `素材版本 ${item.assetVersionId ?? '未记录'}`,
    role: roles[item.mediaRole] || item.mediaRole || '参考素材',
    index: index + 1,
  }))
  function text(node) {
    if (!node || typeof node !== 'object') return ''
    if (node.type === 'text') return typeof node.text === 'string' ? node.text : ''
    if (node.type === 'mention') {
      const matches = references.filter(item => item.key === String(node.referenceKey))
      return matches.length ? `@${matches.map(item => item.name).join('、')}` : '[未记录名称的引用]'
    }
    if (node.type === 'hardBreak') return '\n'
    return Array.isArray(node.content) ? node.content.map(text).join(node.type === 'doc' ? '\n' : '') : ''
  }
  const parameters = Object.entries(input.parameters || {}).map(([key, value]) => ({
    key, label: labels[key] || key,
    value: value == null ? '未记录' : typeof value === 'boolean' ? (value ? '开启' : '关闭') : ['duration', 'duration_seconds'].includes(key) ? `${value} 秒` : String(value),
  }))
  return { prompt: typeof input.prompt === 'string' ? input.prompt : text(input.prompt), references, parameters }
}
