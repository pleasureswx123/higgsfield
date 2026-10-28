export interface ServerEvent {
  event: string
  data: string
  id?: string
}

// 按行解析SSE，保留跨网络分片的UTF-8字符和CRLF，空行才提交事件。
export async function* parseEventStream(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<ServerEvent> {
  const reader = body.getReader(),
    decoder = new TextDecoder()
  let buffer = '',
    event = 'message',
    id: string | undefined,
    data: string[] = [],
    size = 0
  try {
    while (true) {
      const chunk = await reader.read()
      if (chunk.done) break
      buffer += decoder.decode(chunk.value, { stream: true })
      if (buffer.length + size > 8 * 1024 * 1024) throw new Error('任务事件过大，请重新加载详情')
      while (true) {
        const index = buffer.search(/[\r\n]/)
        if (index < 0 || (buffer[index] === '\r' && index === buffer.length - 1)) break
        const line = buffer.slice(0, index)
        buffer = buffer.slice(
          index + (buffer[index] === '\r' && buffer[index + 1] === '\n' ? 2 : 1),
        )
        if (!line) {
          if (data.length) yield { event, data: data.join('\n'), id }
          event = 'message'
          data = []
          size = 0
        } else if (!line.startsWith(':')) {
          const colon = line.indexOf(':')
          const field = colon < 0 ? line : line.slice(0, colon)
          const value = colon < 0 ? '' : line.slice(colon + 1).replace(/^ /, '')
          if (field === 'data') {
            data.push(value)
            size += value.length
          }
          if (field === 'event') event = value || 'message'
          if (field === 'id' && !value.includes('\0')) id = value
        }
      }
    }
  } finally {
    await reader.cancel().catch(() => {})
    reader.releaseLock()
  }
}
