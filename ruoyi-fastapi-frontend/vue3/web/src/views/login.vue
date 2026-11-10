<template>
  <main class="login" :class="{ 'is-dark': settings.isDark }">
    <header class="login-header">
      <div class="brand"><NightmareLogo class="login-brand-logo" /><span>管理平台</span></div>
      <el-button class="theme-toggle" text @click="settings.toggleTheme()">{{ settings.isDark ? '切换亮色' : '切换暗色' }}</el-button>
    </header>
    <section class="login-layout">
      <div class="intro">
        <span class="eyebrow">AI 创作 · 有序协作</span>
        <h1>让灵感成像，<br />让创作发生。</h1>
        <p>连接图片与视频模型，<br />让团队专注每一次创作。</p>
        <div class="intro-tags"><span>模型接入</span><span>团队管理</span><span>用量与费用</span></div>
      </div>
    <el-form
      ref="loginRef"
      :model="loginForm"
      :rules="loginRules"
      class="login-form"
      label-position="top"
      @submit.prevent="handleLogin"
    >
      <div class="form-heading"><h2>欢迎回来</h2><p>登录 Nightmare Theatre 管理平台</p></div>
      <el-form-item prop="username" label="账号">
        <el-input
          v-model="loginForm.username"
          type="text"
          size="large"
          auto-complete="off"
          placeholder="请输入账号"
          aria-label="账号"
        >
          <template #prefix
            ><svg-icon
              icon-class="user"
              class="el-input__icon input-icon"
          /></template>
        </el-input>
      </el-form-item>
      <el-form-item prop="password" label="密码">
        <el-input
          v-model="loginForm.password"
          type="password"
          size="large"
          auto-complete="off"
          placeholder="请输入密码"
          aria-label="密码"
          show-password
          @keyup.enter="handleLogin"
        >
          <template #prefix
            ><svg-icon
              icon-class="password"
              class="el-input__icon input-icon"
          /></template>
        </el-input>
      </el-form-item>
      <el-form-item
        prop="code"
        label="验证码"
        v-if="captchaEnabled"
      >
        <el-input
          v-model="loginForm.code"
          size="large"
          auto-complete="off"
          placeholder="验证码"
          style="width: 63%"
          @keyup.enter="handleLogin"
        >
          <template #prefix
            ><svg-icon
              icon-class="validCode"
              class="el-input__icon input-icon"
          /></template>
        </el-input>
        <button type="button" class="login-code" aria-label="更换验证码" @click="getCode">
          <img
            :src="codeUrl"
            alt="验证码"
            class="login-code-img"
          />
        </button>
      </el-form-item>
      <el-checkbox
        v-model="loginForm.rememberMe"
        style="margin: 0px 0px 25px 0px"
        >记住密码</el-checkbox
      >
      <el-form-item style="width: 100%">
        <el-button
          class="login-submit"
          :loading="loading"
          size="large"
          type="primary"
          style="width: 100%"
          @click.prevent="handleLogin"
        >
          <span v-if="!loading">登录</span>
          <span v-else>正在登录…</span>
        </el-button>
        <div
          style="float: right"
          v-if="register"
        >
          <router-link
            class="link-type"
            :to="'/register'"
            >立即注册</router-link
          >
        </div>
      </el-form-item>
    </el-form>
    </section>
    <footer class="login-footer">Nightmare Theatre · AI 图片与视频制作平台</footer>
  </main>
</template>

<script setup>
import NightmareLogo from '@/layout/components/Sidebar/NightmareLogo.vue'
import { getCodeImg } from '@/api/login'
import Cookies from 'js-cookie'
import { encrypt, decrypt } from '@/utils/jsencrypt'
import useUserStore from '@/store/modules/user'
import useSettingsStore from '@/store/modules/settings'

const settings = useSettingsStore()
const userStore = useUserStore()
const route = useRoute()
const router = useRouter()
const { proxy } = getCurrentInstance()

const loginForm = ref({
  username: '',
  password: '',
  rememberMe: false,
  code: '',
  uuid: '',
})

const loginRules = {
  username: [{ required: true, trigger: 'blur', message: '请输入您的账号' }],
  password: [{ required: true, trigger: 'blur', message: '请输入您的密码' }],
  code: [{ required: true, trigger: 'change', message: '请输入验证码' }],
}

const codeUrl = ref('')
const loading = ref(false)
// 验证码开关
const captchaEnabled = ref(true)
// 注册开关
const register = ref(false)
const redirect = ref(undefined)

watch(
  route,
  (newRoute) => {
    redirect.value = newRoute.query && newRoute.query.redirect
  },
  { immediate: true }
)

function handleLogin() {
  if (loading.value) return
  proxy.$refs.loginRef.validate((valid) => {
    if (valid) {
      loading.value = true
      // 勾选了需要记住密码设置在 cookie 中设置记住用户名和密码
      if (loginForm.value.rememberMe) {
        Cookies.set('username', loginForm.value.username, { expires: 30 })
        Cookies.set('password', encrypt(loginForm.value.password), { expires: 30 })
        Cookies.set('rememberMe', loginForm.value.rememberMe, { expires: 30 })
      } else {
        // 否则移除
        Cookies.remove('username')
        Cookies.remove('password')
        Cookies.remove('rememberMe')
      }
      // 调用action的登录方法
      userStore
        .login(loginForm.value)
        .then(() => {
          const query = route.query
          const otherQueryParams = Object.keys(query).reduce((acc, cur) => {
            if (cur !== 'redirect') {
              acc[cur] = query[cur]
            }
            return acc
          }, {})
          router.push({ path: redirect.value || '/', query: otherQueryParams })
        })
        .catch(() => {
          loading.value = false
          // 重新获取验证码
          if (captchaEnabled.value) {
            getCode()
          }
        })
    }
  })
}

function getCode() {
  getCodeImg().then((res) => {
    captchaEnabled.value = res.captchaEnabled === undefined ? true : res.captchaEnabled
    register.value = res.registerEnabled === undefined ? false : res.registerEnabled
    if (captchaEnabled.value) {
      codeUrl.value = 'data:image/gif;base64,' + res.img
      loginForm.value.uuid = res.uuid
    }
  })
}

function getCookie() {
  const username = Cookies.get('username')
  const password = Cookies.get('password')
  const rememberMe = Cookies.get('rememberMe')
  loginForm.value = {
    username: username === undefined ? loginForm.value.username : username,
    password: password === undefined ? loginForm.value.password : decrypt(password),
    rememberMe: rememberMe === undefined ? false : Boolean(rememberMe),
  }
}

getCode()
getCookie()
</script>

<style lang="scss" scoped>
.login {
  --login-bg: #f4f6f2; --login-surface: #ffffff; --login-text: #152b28;
  --login-muted: #63756f; --login-line: #dce4dd; --login-accent: #235b4d;
  min-height: 100vh; min-height: 100dvh; display: flex; flex-direction: column;
  padding: 32px 5vw 20px; color: var(--login-text); background: var(--login-bg);
  background-image: radial-gradient(ellipse at 12% 45%, #c8d9bd50, transparent 55%);
}
.login.is-dark {
  --login-bg: #101513; --login-surface: #19201c; --login-text: #eff4e9;
  --login-muted: #a2afa5; --login-line: #344036; --login-accent: #d0e77b;
  background-image: radial-gradient(ellipse at 12% 45%, #536a2926, transparent 55%);
}
.login-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.brand { display: flex; align-items: center; gap: 12px; }
.brand .login-brand-logo { display:block; width:clamp(150px, 20vw, 220px); height:auto; flex-shrink:1; }
.brand span { flex-shrink: 0; border-left: 1px solid var(--login-line); padding-left: 14px; font-size: 13px; color: var(--login-muted); }
.theme-toggle { color: var(--login-muted); }
.login-layout { flex: 1; width: 100%; max-width: 1100px; margin: auto; display: grid; grid-template-columns: 1fr 420px; gap: 80px; align-items: center; padding: 64px 0; }
.eyebrow { font-size: 12px; letter-spacing: 2px; color: var(--login-accent); font-weight: 600; }
.intro h1 { font-size: clamp(36px, 4.2vw, 58px); line-height: 1.3; letter-spacing: -2px; font-weight: 600; margin: 24px 0; }
.intro p { color: var(--login-muted); font-size: 17px; line-height: 1.9; }
.intro-tags { display: flex; flex-wrap: wrap; gap: 24px; margin-top: 42px; color: var(--login-muted); font-size: 13px; }
.intro-tags span::before { content: ''; display: inline-block; width: 5px; height: 5px; border-radius: 50%; margin: 0 8px 2px 0; background: var(--login-accent); }
.login-form { align-self: center; width: 100%; min-width: 0; background: var(--login-surface); border: 1px solid var(--login-line); border-radius: 16px; padding: 36px 36px 16px; box-shadow: 0 12px 40px #00000006; }
.form-heading { margin-bottom: 28px; }
.form-heading h2 { font-size: 26px; font-weight: 600; margin: 0 0 10px; color: var(--login-text); }
.form-heading p { margin: 0; color: var(--login-muted); font-size: 14px; }
.login-form :deep(.el-form-item__label), .login-form :deep(.el-checkbox__label) { color: var(--login-muted); }
.login-form :deep(.el-input) { --el-input-height: 46px; height: 46px; flex: 0 1 auto; }
.login-form :deep(.el-input__wrapper) { height: 46px; min-height: 0; padding: 0 14px; box-sizing: border-box; background: var(--login-surface); box-shadow: 0 0 0 1px var(--login-line) inset; border-radius: 8px; }
.login-form :deep(.el-input__wrapper.is-focus) { box-shadow: 0 0 0 2px var(--login-accent) inset; }
.login-form :deep(.el-input__inner) { height: 44px; line-height: 44px; color: var(--login-text); }
.login-form :deep(.el-input__prefix), .login-form :deep(.el-input__suffix) { height: 44px; align-items: center; }
.login-form :deep(.el-input__inner::placeholder) { color: var(--login-muted); }
.login-form :deep(.el-form-item) { margin-bottom: 22px; }
.login-submit { --el-button-bg-color: #d0e77b; --el-button-border-color: #d0e77b; --el-button-text-color: #203120; --el-button-hover-bg-color: #ddef9d; --el-button-hover-border-color: #ddef9d; --el-button-hover-text-color: #203120; --el-button-active-bg-color: #bdd468; --el-button-active-border-color: #bdd468; height: 46px; border-radius: 8px; font-weight: 600; }
.input-icon { width: 16px; height: 16px; flex-shrink: 0; }
.login-code { width: 33%; height: 46px; padding: 0; margin-left: 4%; border: 1px solid var(--login-line); border-radius: 8px; overflow: hidden; background: white; cursor: pointer; }
.login-code-img { width: 100%; height: 100%; object-fit: contain; }
.login-footer { text-align: center; color: var(--login-muted); font-size: 12px; padding: 12px; }
@media (max-width: 850px) { .login-layout { grid-template-columns: minmax(0, 420px); justify-content: center; gap: 0; padding: 48px 0; } .intro { display: none; } }
@media (max-width: 480px) { .login { padding: 20px 20px 12px; } .brand span { display: none; } .login-form { padding: 28px 22px; border-radius: 16px; } }
</style>
