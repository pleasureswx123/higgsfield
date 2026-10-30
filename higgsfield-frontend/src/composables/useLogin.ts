import { ref, reactive, computed, onMounted } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { getCaptcha } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
export function useLogin() {
  const form = ref<FormInstance>()
  const values = reactive({ username: '', password: '', code: '', uuid: '' })
  const captchaEnabled = ref(true),
    captchaImage = ref(''),
    captchaLoading = ref(false),
    ready = ref(false),
    pending = ref(false),
    error = ref('')
  const auth = useAuthStore(),
    router = useRouter(),
    route = useRoute()
  const rules: FormRules = {
    username: [{ required: true, whitespace: true, message: '请输入账号', trigger: 'blur' }],
    password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
    code: [
      {
        validator: (_rule, value, done) =>
          captchaEnabled.value && !String(value).trim() ? done(new Error('请输入验证码')) : done(),
        trigger: 'blur',
      },
    ],
  }
  async function refreshCaptcha() {
    if (captchaLoading.value) return
    captchaLoading.value = true
    ready.value = false
    values.code = ''
    try {
      const data = await getCaptcha()
      captchaEnabled.value = data.captchaEnabled
      captchaImage.value = `data:image/png;base64,${data.img}`
      values.uuid = data.uuid
      ready.value = true
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : '验证码加载失败'
    } finally {
      captchaLoading.value = false
    }
  }
  async function submit() {
    if (pending.value || !ready.value) return
    if (!(await form.value?.validate().catch(() => false))) return
    pending.value = true
    error.value = ''
    try {
      await auth.signIn(values)
      values.password = ''
      const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/home'
      await router.replace(
        redirect.startsWith('/') && !redirect.startsWith('//') && redirect !== '/login'
          ? redirect
          : '/home',
      )
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : '登录失败'
      await refreshCaptcha()
    } finally {
      pending.value = false
    }
  }
  const restoreError = computed(() => auth.restoreError)
  async function retrySession() {
    if (pending.value) return
    pending.value = true
    try {
      await auth.restoreSession()
      if (auth.isAuthenticated) {
        const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/home'
        await router.replace(redirect.startsWith('/') && !redirect.startsWith('//') && !redirect.startsWith('/login') ? redirect : '/home')
      }
    } finally { pending.value = false }
  }
  onMounted(refreshCaptcha)
  return {
    form,
    values,
    rules,
    captchaEnabled,
    captchaImage,
    captchaLoading,
    ready,
    pending,
    error,
    refreshCaptcha,
    restoreError,
    retrySession,
    submit,
  }
}
