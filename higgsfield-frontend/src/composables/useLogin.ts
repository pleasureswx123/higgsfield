import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { getCaptcha } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import { forgetLogin, readRememberedLogin, rememberLogin, rememberPeriod } from '@/utils/rememberedLogin'

export function useLogin() {
  const form = ref<FormInstance>()
  const values = reactive({ username: '', password: '', code: '', uuid: '' })
  const remember = ref(false)
  let savedIdentity: { username: string; expires: number } | undefined
  let rememberTouched = false
  function setRemember(checked: boolean | 'indeterminate') {
    rememberTouched = true
    remember.value = checked === true
    if (!remember.value) {
      savedIdentity = undefined
      try { forgetLogin() } catch { ElMessage.warning('浏览器限制存储，请在浏览器设置中清除本网站数据。') }
    }
  }
  async function restoreCredentials() {
    try {
      const saved = await readRememberedLogin()
      if (saved && !rememberTouched && !pending.value && (!values.username || values.username === saved.username)
        && (!values.password || values.password === saved.password)) {
        savedIdentity = { username: saved.username, expires: saved.expires }
        values.username = saved.username
        values.password = saved.password
        remember.value = true
      }
    } catch { /* 禁用浏览器存储时仍可手动登录。 */ }
  }
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
    if (pending.value) return
    pending.value = true
    rememberTouched = true
    error.value = ''
    try {
      const input = { ...values, username: values.username.trim() }
      const expires = savedIdentity?.username === input.username && savedIdentity.expires > Date.now()
        ? savedIdentity.expires : Date.now() + rememberPeriod
      await auth.signIn(input)
      try {
        if (remember.value) {
          await rememberLogin({ username: input.username, password: input.password }, expires)
          await auth.rememberSession(expires)
        }
        else forgetLogin()
      } catch {
        ElMessage.warning('已登录，但浏览器未能保存本次记住密码设置。')
      }
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
  onMounted(restoreCredentials)
  onMounted(refreshCaptcha)
  return {
    form,
    values,
    remember,
    setRemember,
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
