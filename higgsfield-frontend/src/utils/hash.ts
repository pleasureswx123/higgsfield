export function hashBlob(
  file: Blob,
  signal: AbortSignal,
  progress: (value: number) => void = () => {},
): Promise<string> {
  return new Promise((resolve, reject) => {
    const worker = new Worker(new URL('../workers/hash.worker.ts', import.meta.url), {
      type: 'module',
    })
    const cleanup = () => {
      worker.terminate()
      signal.removeEventListener('abort', abort)
    }
    const abort = () => {
      cleanup()
      reject(new DOMException('已暂停', 'AbortError'))
    }
    worker.onmessage = ({ data }) => {
      if (data.digest) {
        cleanup()
        resolve(data.digest)
      } else if (data.error) {
        cleanup()
        reject(new Error(data.error))
      } else progress(data.progress)
    }
    worker.onerror = () => {
      cleanup()
      reject(new Error('文件校验线程启动失败'))
    }
    signal.addEventListener('abort', abort, { once: true })
    if (signal.aborted) abort()
    else worker.postMessage(file)
  })
}
