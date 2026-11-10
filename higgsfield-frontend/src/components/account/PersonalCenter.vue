<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'
import { IconEye, IconEyeOff } from '@tabler/icons-vue'
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import Button from '@/components/ui/Button.vue'
import { usePersonalCenter } from '@/composables/usePersonalCenter'

defineOptions({ name: 'PersonalCenter' })

const route = useRoute(), router = useRouter(), auth = useAuthStore()
const center = usePersonalCenter()
const { loading, saving, ready, error, notice, userName, form, password, fields, dirty, passwordDirty } = center
const tab = ref(route.query.tab === 'password' ? 'password' : 'profile'), discardOpen = ref(false)
const visiblePasswords = ref<Record<string, boolean>>({})
const passwordFields = [
  { key: 'oldPassword', label: '当前密码', autocomplete: 'current-password' },
  { key: 'newPassword', label: '新密码', autocomplete: 'new-password' },
  { key: 'confirmPassword', label: '确认新密码', autocomplete: 'new-password' },
] as const
onMounted(() => { void center.load(); window.addEventListener('beforeunload', beforeUnload) })
let resolveLeave: ((value: boolean) => void) | undefined
onBeforeUnmount(() => { window.removeEventListener('beforeunload', beforeUnload); resolveLeave?.(false) })
function beforeUnload(event: BeforeUnloadEvent) {
  if (dirty.value || passwordDirty.value) { event.preventDefault(); event.returnValue = '' }
}
onBeforeRouteLeave(() => {
  if (!auth.isAuthenticated) return true
  if (saving.value) return false
  if (!dirty.value && !passwordDirty.value) return true
  discardOpen.value = true
  return new Promise<boolean>(resolve => { resolveLeave = resolve })
})
watch(discardOpen, value => { if (!value) { resolveLeave?.(false); resolveLeave = undefined } })
watch(tab, () => { center.clearFeedback(); visiblePasswords.value = {} })
watch(() => route.query.tab, value => { tab.value = value === 'password' ? 'password' : 'profile' })
function discard() { resolveLeave?.(true); resolveLeave = undefined; discardOpen.value = false }
function goBack() {
  const target = route.query.from
  void router.push(typeof target === 'string' && /^\/(home|projects)([/?]|$)/.test(target) ? target : '/home')
}
async function changePassword() {
  if (await center.savePassword()) {
    ElMessage.success('密码已修改，请重新登录')
    await auth.signOut().catch(() => {})
    await router.replace('/login')
  }
}
</script>

<template>
  <section class="personal-center">
      <header class="personal-header"><h1 class="personal-title">个人中心</h1><Button variant="outline" @click="goBack">返回</Button></header>
      <Tabs v-model="tab">
        <TabsList class="studio-tabs studio-pill-tabs personal-tabs">
          <TabsTrigger value="profile" :disabled="saving">基本资料</TabsTrigger>
          <TabsTrigger value="password" :disabled="saving">修改密码</TabsTrigger>
        </TabsList>
        <p v-if="loading" role="status">正在加载个人资料…</p>
        <p v-if="error" role="alert" class="personal-error">{{ error }}</p>
        <p v-if="notice" role="status" class="personal-notice">{{ notice }}</p>
        <Button v-if="!loading && !ready" variant="outline" @click="center.load">重新加载</Button>
        <template v-if="ready">
          <TabsContent value="profile">
            <form class="personal-form" @submit.prevent="center.saveProfile">
              <div class="personal-field"><span class="personal-account-label">登录账号</span><p class="personal-account">{{ userName }}</p></div>
              <div class="personal-field"><Label for="profile-name">昵称</Label><Input id="profile-name" v-model="form.nickName" :disabled="saving" maxlength="30" autocomplete="nickname" :aria-invalid="!!fields.nickName" aria-describedby="profile-name-error" /><p v-if="fields.nickName" id="profile-name-error" class="personal-error">{{ fields.nickName }}</p></div>
              <div class="personal-field"><Label for="profile-phone">手机号码</Label><Input id="profile-phone" v-model="form.phonenumber" :disabled="saving" maxlength="11" type="tel" autocomplete="tel" placeholder="选填" :aria-invalid="!!fields.phonenumber" aria-describedby="profile-phone-error" /><p v-if="fields.phonenumber" id="profile-phone-error" class="personal-error">{{ fields.phonenumber }}</p></div>
              <div class="personal-field"><Label for="profile-email">邮箱</Label><Input id="profile-email" v-model="form.email" :disabled="saving" maxlength="50" type="email" autocomplete="email" placeholder="选填" :aria-invalid="!!fields.email" aria-describedby="profile-email-error" /><p v-if="fields.email" id="profile-email-error" class="personal-error">{{ fields.email }}</p></div>
              <div class="personal-footer"><Button type="submit" :disabled="saving || !dirty">{{ saving ? '正在保存…' : '保存修改' }}</Button></div>
            </form>
          </TabsContent>
          <TabsContent value="password">
            <form class="personal-form" @submit.prevent="changePassword">
              <div v-for="field in passwordFields" :key="field.key" class="personal-field">
                <Label :for="`profile-${field.key}`">{{ field.label }}</Label>
                <div class="personal-password">
                  <Input :id="`profile-${field.key}`" v-model="password[field.key]" :disabled="saving" :type="visiblePasswords[field.key] ? 'text' : 'password'" :autocomplete="field.autocomplete" :aria-invalid="!!fields[field.key]" :aria-describedby="`profile-${field.key}-error`" />
                  <Button type="button" variant="ghost" :aria-label="`${visiblePasswords[field.key] ? '隐藏' : '显示'}${field.label}`" :aria-pressed="!!visiblePasswords[field.key]" @click="visiblePasswords[field.key] = !visiblePasswords[field.key]"><component :is="visiblePasswords[field.key] ? IconEyeOff : IconEye" :size="18" /></Button>
                </div>
                <p v-if="fields[field.key]" :id="`profile-${field.key}-error`" class="personal-error">{{ fields[field.key] }}</p>
              </div>
              <p class="personal-hint">修改成功后需要重新登录。</p>
              <div class="personal-footer"><Button type="submit" :disabled="saving || dirty">{{ saving ? '正在修改…' : '修改密码' }}</Button></div>
              <p v-if="dirty" class="personal-hint">基本资料尚未保存，请先保存基本资料。</p>
            </form>
          </TabsContent>
        </template>
      </Tabs>
  </section>
  <Dialog v-model:open="discardOpen">
    <DialogContent class="studio-dialog personal-discard">
      <DialogTitle>放弃未保存的修改？</DialogTitle>
      <DialogDescription>离开后，本次未保存的内容将不会保留。</DialogDescription>
      <div class="personal-footer"><Button variant="outline" @click="discardOpen = false">继续编辑</Button><Button @click="discard">放弃修改</Button></div>
    </DialogContent>
  </Dialog>
</template>

<style scoped>
.personal-center { width:100%; max-width:760px; margin:0 auto; padding:32px; color:var(--foreground); }
.personal-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:24px; }
.personal-title { margin:0; font-size:22px; font-weight:650; }
.personal-form { max-width:520px; }
.personal-tabs { margin-bottom:24px; }
.personal-form { display:flex; flex-direction:column; gap:22px; }
.personal-field { display:flex; flex-direction:column; gap:9px; }
.personal-field label { font-size:13px; }


.personal-account-label { font-size:13px; color:var(--muted-foreground); }
.personal-account { margin:0; padding-bottom:16px; border-bottom:1px solid var(--border); font-size:14px; overflow-wrap:anywhere; }
.personal-password { position:relative; }
.personal-password input { padding-right:44px; }
.personal-password .ui-button { position:absolute; right:2px; top:2px; width:32px; height:32px; min-height:0; padding:0; color:var(--muted-foreground); }
.personal-footer { display:flex; justify-content:flex-end; gap:10px; margin-top:8px; }
.personal-error { font-size:13px; color:var(--destructive); margin:0 0 8px; overflow-wrap:anywhere; }
.personal-notice { font-size:13px; margin:0 0 20px; }
.personal-hint { font-size:12px; color:var(--muted-foreground); margin:0; }
:global(.personal-discard) { max-width:400px; }
@media (max-width:480px) { .personal-center { padding:24px 20px; } }
</style>
