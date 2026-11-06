import { ref } from 'vue'
import { ApiError } from '@/api/client'
import { subscribeProjectActivity } from '@/api/generations'

/** 一个工作区一条连接；失效通知不承载任务正文，重连始终补查授权快照。 */
export function useProjectActivityEvents(project: () => string, enabled: () => boolean,
  changed: () => void, revoked: () => void, disconnected: () => void) {
  const connected = ref(false)
  let controller: AbortController | undefined
  let retry: ReturnType<typeof setTimeout> | undefined
  let watchdog: ReturnType<typeof setTimeout> | undefined
  let failures = 0
  function stop() {
    const previous = controller
    controller = undefined
    previous?.abort()
    clearTimeout(retry); clearTimeout(watchdog); connected.value = false
  }
  function start() {
    if (!enabled() || controller) return
    clearTimeout(retry)
    const current = new AbortController(), identity = project()
    controller = current
    const alive = () => controller === current && enabled() && project() === identity
    function arm() {
      clearTimeout(watchdog)
      watchdog = setTimeout(() => { if (alive()) current.abort() }, 45000)
    }
    arm()
    void (async () => {
      try {
        await subscribeProjectActivity(identity, current.signal, async event => {
          if (!alive() || current.signal.aborted) return
          if (event.event === 'access.revoked') { stop(); revoked(); return }
          const payload = JSON.parse(event.data)
          if (payload.projectId !== identity) throw new Error('项目事件身份不匹配')
          if (event.event === 'activity.degraded') throw new Error('实时状态服务暂不可用')
          if (!['activity.sync', 'activity.changed', 'activity.heartbeat'].includes(event.event)) throw new Error('项目事件格式不受支持')
          failures = 0; connected.value = true; arm()
          if (event.event !== 'activity.heartbeat') changed()
        })
      } catch (cause) {
        if (!alive()) return
        if (cause instanceof ApiError && (cause.code === 401 || cause.code === 403 || cause.errorCode === 'RESOURCE_NOT_FOUND')) {
          stop(); revoked(); return
        }
      } finally {
        if (alive()) {
          clearTimeout(watchdog); controller = undefined; connected.value = false
          disconnected()
          failures++
          retry = setTimeout(start, Math.min(30000, 2000 * 2 ** (Math.min(failures, 5) - 1)) + Math.floor(Math.random() * 1000))
        }
      }
    })()
  }
  return { connected, start, stop }
}
