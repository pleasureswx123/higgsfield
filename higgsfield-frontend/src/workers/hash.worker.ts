import { sha256 } from '@noble/hashes/sha2.js'

// 在工作线程逐块计算，避免大视频完整进入主线程内存。
self.onmessage = async (event: MessageEvent<Blob>) => {
  try {
    const file = event.data
    const hash = sha256.create()
    const chunk = 4 * 1024 * 1024
    for (let offset = 0; offset < file.size; offset += chunk) {
      hash.update(new Uint8Array(await file.slice(offset, offset + chunk).arrayBuffer()))
      self.postMessage({ progress: Math.min(offset + chunk, file.size) / file.size })
    }
    self.postMessage({
      digest: Array.from(hash.digest(), (byte) => byte.toString(16).padStart(2, '0')).join(''),
    })
  } catch {
    self.postMessage({ error: '无法读取文件，请重新选择' })
  }
}
