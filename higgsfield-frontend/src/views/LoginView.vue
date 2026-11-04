<script setup lang="ts">
import { ElForm, ElFormItem } from 'element-plus'
import { ref, reactive } from 'vue'
import { Card, CardHeader, CardContent, CardTitle, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import Button from '@/components/ui/Button.vue'
import { IconArrowRight, IconRefresh, IconEye, IconEyeOff, IconLoader2, IconAlertCircle } from '@tabler/icons-vue'
import '@/styles/login.css'
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
const passwordVisible = ref(false)
const fieldErrors = reactive<Record<string, string>>({})
function validateField(field: string) {
  void form.value?.validateField(field).catch(() => undefined)
}
function trackValidation(field: string | string[], valid: boolean, message: string) {
  fieldErrors[String(field)] = valid ? '' : message
}
</script>
<template>
  <div class="login-page login-showcase">
    <img class="login-backdrop" src="/images/login-cosmos.webp" alt="" aria-hidden="true" />
    <main class="login-main">
      <section class="login-intro" aria-label="创作灵感">
        <img class="login-scene" src="/images/login-cosmos.webp" alt="星空下的岩石峡谷，远处行星与暖色地平线" fetchpriority="high" />
        <div class="login-art-heading"><span>想象，没有边界。</span><span class="login-art-caption">HIGGSFIELD STUDIO</span></div>
        <div class="login-art-copy">
          <span class="eyebrow">从灵感，到作品</span>
          <h1>让想象<br />成为画面<span class="accent">。</span></h1>
          <p>在统一的创作空间，连接你的团队与作品。</p>
          <div class="intro-foot"><span>构思</span><IconArrowRight :size="14" /><span>创作</span><IconArrowRight :size="14" /><span>协作</span></div>
        </div>
      </section>
      <section class="login-panel">
        <header class="login-header">
          <a href="/" class="brand"><img src="/brand-mark.svg" width="32" height="32" alt="Higgsfield 制作平台" /><span>Higgsfield <small>STUDIO</small></span></a>
        </header>
      <Card class="login-card" aria-labelledby="login-title">
        <CardHeader class="login-card-header">
          <span class="eyebrow">你的下一部作品，从这里开始</span>
          <CardTitle id="login-title" as="h2">欢迎回来。</CardTitle>
          <CardDescription>使用公司分配的账号继续创作</CardDescription>
        </CardHeader>
        <CardContent class="login-card-content">
          <Alert v-if="restoreError" class="login-alert">
            <IconAlertCircle :size="16" /><AlertDescription>{{ restoreError }}</AlertDescription>
          </Alert>
          <Button v-if="restoreError" type="button" variant="outline" :disabled="pending" @click="retrySession">重试恢复登录</Button>
          <Alert v-if="error" variant="destructive" class="login-alert">
            <IconAlertCircle :size="16" /><AlertDescription>{{ error }}</AlertDescription>
          </Alert>
          <ElForm ref="form" :model="values" :rules="rules" label-position="top" @validate="trackValidation" @submit.prevent="submit">
            <Label for="login-username" class="login-label">账号</Label>
            <ElFormItem prop="username">
              <Input id="login-username" v-model="values.username" autocomplete="username" placeholder="请输入账号" :disabled="pending" aria-required="true" :aria-invalid="!!fieldErrors.username" :aria-describedby="fieldErrors.username ? 'login-username-error' : undefined" @blur="validateField('username')" />
              <template #error="{ error: message }"><span id="login-username-error" class="el-form-item__error" role="alert">{{ message }}</span></template>
            </ElFormItem>
            <Label for="login-password" class="login-label">密码</Label>
            <ElFormItem prop="password">
              <div class="login-password">
                <Input id="login-password" v-model="values.password" :type="passwordVisible ? 'text' : 'password'" autocomplete="current-password" placeholder="请输入密码" :disabled="pending" aria-required="true" :aria-invalid="!!fieldErrors.password" :aria-describedby="fieldErrors.password ? 'login-password-error' : undefined" @blur="validateField('password')" />
                <Button type="button" variant="ghost" class="login-password-toggle" :disabled="pending" :aria-label="passwordVisible ? '隐藏密码' : '显示密码'" :aria-pressed="passwordVisible" @click="passwordVisible = !passwordVisible"><IconEyeOff v-if="passwordVisible" :size="17" /><IconEye v-else :size="17" /></Button>
              </div>
              <template #error="{ error: message }"><span id="login-password-error" class="el-form-item__error" role="alert">{{ message }}</span></template>
            </ElFormItem>
            <template v-if="captchaEnabled">
              <Label for="login-code" class="login-label">验证码</Label>
              <ElFormItem prop="code">
                <div class="captcha-row">
                  <Input id="login-code" v-model="values.code" autocomplete="off" placeholder="验证码" :disabled="pending" aria-required="true" :aria-invalid="!!fieldErrors.code" :aria-describedby="fieldErrors.code ? 'login-code-error' : undefined" @blur="validateField('code')" />
                  <Button type="button" variant="outline" class="captcha-button" :disabled="captchaLoading || pending" aria-label="刷新验证码" title="点击刷新验证码" @click="refreshCaptcha">
                    <img v-if="captchaImage && !captchaLoading" :src="captchaImage" alt="登录验证码" /><IconRefresh v-else :size="22" />
                  </Button>
                </div>
                <template #error="{ error: message }"><span id="login-code-error" class="el-form-item__error" role="alert">{{ message }}</span></template>
              </ElFormItem>
            </template>
            <Button type="submit" class="login-submit" :disabled="pending || !ready || captchaLoading" :aria-busy="pending"><IconLoader2 v-if="pending" :size="18" class="animate-spin" />{{ pending ? '正在登录' : '登录并开始创作' }}<IconArrowRight v-if="!pending" :size="18" /></Button>
            <Button v-if="!ready && !captchaLoading" type="button" variant="ghost" @click="refreshCaptcha">重新连接服务</Button>
          </ElForm>
          <p class="login-help">无法登录？请联系管理员检查账号与权限。</p>
        </CardContent>
      </Card>
        <footer class="login-footer">创作，从这里发生。</footer>
      </section>
    </main>
  </div>
</template>
