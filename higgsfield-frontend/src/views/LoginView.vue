<script setup lang="ts">
import { ElForm, ElFormItem, ElInput, ElButton, ElAlert } from 'element-plus'
import { IconAperture, IconArrowRight, IconRefresh } from '@tabler/icons-vue'
import ThemeToggle from '@/components/shared/ThemeToggle.vue'
import { useLogin } from '@/composables/useLogin'
const {
  form,
  values,
  rules,
  captchaEnabled,
  captchaImage,
  captchaLoading,
  ready,
  pending,
  error,
  restoreError,
  retrySession,
  refreshCaptcha,
  submit,
} = useLogin()
</script>
<template>
  <div class="login-page">
    <header class="login-header">
      <a href="/" class="brand"
        ><IconAperture :size="30" /><span>Higgsfield <small>STUDIO</small></span></a
      ><ThemeToggle />
    </header>
    <main class="login-main">
      <section class="login-intro">
        <span class="eyebrow">你的下一部作品，从这里开始</span>
        <h1>让想象<br />成为画面<span class="accent">。</span></h1>
        <p>从一个灵感，到一个完整的故事。<br />在统一的创作空间，连接你的团队与作品。</p>
        <div class="intro-foot">
          <span>构思</span><IconArrowRight :size="16" /><span>创作</span
          ><IconArrowRight :size="16" /><span>协作</span>
        </div>
      </section>
      <section class="login-card" aria-labelledby="login-title">
        <span class="eyebrow">欢迎回来</span>
        <h2 id="login-title">登录制作平台</h2>
        <p class="muted">使用公司分配的账号继续创作</p>
        <ElAlert v-if="restoreError" :title="restoreError" type="warning" :closable="false" show-icon />
        <ElButton v-if="restoreError" :loading="pending" @click="retrySession">重试恢复登录</ElButton>
        <ElAlert
          v-if="error"
          :title="error"
          type="error"
          :closable="false"
          show-icon
          role="alert"
        />
        <ElForm
          ref="form"
          :model="values"
          :rules="rules"
          label-position="top"
          size="large"
          @submit.prevent="submit"
        >
          <ElFormItem label="账号" prop="username"
            ><ElInput
              v-model="values.username"
              autocomplete="username"
              placeholder="请输入账号"
              :disabled="pending"
          /></ElFormItem>
          <ElFormItem label="密码" prop="password"
            ><ElInput
              v-model="values.password"
              type="password"
              show-password
              autocomplete="current-password"
              placeholder="请输入密码"
              :disabled="pending"
          /></ElFormItem>
          <ElFormItem v-if="captchaEnabled" label="验证码" prop="code"
            ><div class="captcha-row">
              <ElInput
                v-model="values.code"
                autocomplete="off"
                placeholder="验证码"
                :disabled="pending"
              /><button
                type="button"
                class="captcha-button"
                :disabled="captchaLoading || pending"
                aria-label="刷新验证码"
                title="点击刷新验证码"
                @click="refreshCaptcha"
              >
                <img
                  v-if="captchaImage && !captchaLoading"
                  :src="captchaImage"
                  alt="登录验证码"
                /><IconRefresh v-else :size="22" />
              </button></div
          ></ElFormItem>
          <ElButton
            native-type="submit"
            type="primary"
            class="login-submit"
            :loading="pending"
            :disabled="!ready || captchaLoading"
            >{{ pending ? '正在登录' : '登录并开始创作' }}<IconArrowRight :size="18"
          /></ElButton>
          <button
            v-if="!ready && !captchaLoading"
            type="button"
            class="text-button"
            @click="refreshCaptcha"
          >
            重新连接服务
          </button>
        </ElForm>
        <p class="login-help">无法登录？请联系管理员检查账号与权限。</p>
      </section>
    </main>
    <footer class="login-footer">HIGGSFIELD STUDIO <span>创作，从这里发生。</span></footer>
  </div>
</template>
