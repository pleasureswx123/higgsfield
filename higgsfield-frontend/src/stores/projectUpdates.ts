import { defineStore } from 'pinia'
import { ref } from 'vue'

/** 项目名称及个人偏好变化后，同步刷新各项目入口。 */
export const useProjectUpdatesStore = defineStore('project-updates', () => {
  const revision = ref(0)
  const orderLocked = ref(false)
  function notify() { revision.value++ }
  return { revision, orderLocked, notify }
})
