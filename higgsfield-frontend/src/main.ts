import { createApp, watch } from 'vue'
import { createPinia } from 'pinia'
import 'element-plus/theme-chalk/base.css'
import 'element-plus/theme-chalk/el-form.css'
import 'element-plus/theme-chalk/el-form-item.css'
import 'element-plus/theme-chalk/el-input.css'
import 'element-plus/theme-chalk/el-button.css'
import 'element-plus/theme-chalk/el-alert.css'
import 'element-plus/theme-chalk/el-message.css'
import 'element-plus/theme-chalk/el-message-box.css'
import 'element-plus/theme-chalk/el-dialog.css'
import 'element-plus/theme-chalk/el-drawer.css'
import 'element-plus/theme-chalk/el-overlay.css'
import 'element-plus/theme-chalk/el-select.css'
import 'element-plus/theme-chalk/el-option.css'
import 'element-plus/theme-chalk/el-pagination.css'
import 'element-plus/theme-chalk/el-popper.css'
import 'element-plus/theme-chalk/el-scrollbar.css'
import 'element-plus/theme-chalk/el-checkbox.css'
import 'element-plus/theme-chalk/el-input-number.css'
import 'element-plus/theme-chalk/el-switch.css'
import 'element-plus/theme-chalk/el-date-picker.css'
import 'element-plus/theme-chalk/el-date-picker-panel.css'
import 'element-plus/theme-chalk/el-table.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import './styles/main.css'
import './styles/action-menus.css'
import './styles/controls.css'
import App from './App.vue'
import { router } from './router'
import { deviceSessionKey } from '@/utils/rememberedLogin'
import { configureAuth } from './api/client'
import { useAuthStore } from './stores/auth'
const app = createApp(App)
app.use(createPinia())
const auth = useAuthStore()
configureAuth(
  () => auth.token,
  () => auth.clear(),
)
// 其他标签页退出或切换设备会话时，重新读取当前凭据与权限。
window.addEventListener('storage', event => {
  if ((event.key === deviceSessionKey || event.key === null) && auth.usesDeviceSession()) window.location.reload()
})
watch(() => auth.token, token => {
  const route = router.currentRoute.value
  if (!token && route.meta.requiresAuth) void router.replace({ path: '/login', query: { redirect: route.fullPath } })
})
app.use(router).mount('#app')
