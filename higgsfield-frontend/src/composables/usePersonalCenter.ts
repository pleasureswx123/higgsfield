import { computed, reactive, ref } from 'vue'
import { getProfile, updateProfile, updatePassword, type ProfileInput } from '@/api/profile'
import { useAuthStore } from '@/stores/auth'

export function usePersonalCenter() {
  const auth = useAuthStore()
  const loading = ref(false), saving = ref(false), ready = ref(false)
  const error = ref(''), notice = ref(''), userName = ref('')
  const form = reactive<ProfileInput>({ nickName: '', phonenumber: '', email: '' })
  const password = reactive({ oldPassword: '', newPassword: '', confirmPassword: '' })
  const baseline = ref('')
  const dirty = computed(() => ready.value && JSON.stringify(form) !== baseline.value)
  const passwordDirty = computed(() => Object.values(password).some(Boolean))
  const fields = reactive<Record<string, string>>({})
  function clearFeedback() { error.value = ''; notice.value = ''; Object.keys(fields).forEach(key => delete fields[key]) }
  function clearPassword() { password.oldPassword = ''; password.newPassword = ''; password.confirmPassword = '' }
  async function load() {
    loading.value = true; ready.value = false; clearFeedback(); clearPassword()
    try {
      const { data } = await getProfile()
      userName.value = data.userName
      Object.assign(form, { nickName: data.nickName || '', phonenumber: data.phonenumber || '', email: data.email || '' })
      baseline.value = JSON.stringify(form); ready.value = true
    } catch (cause) { error.value = cause instanceof Error ? cause.message : '个人资料加载失败，请重试' }
    finally { loading.value = false }
  }
  async function saveProfile() {
    if (saving.value || !ready.value || !dirty.value) return
    clearFeedback()
    const input = { nickName: form.nickName.trim(), phonenumber: form.phonenumber.trim(), email: form.email.trim() }
    if (!input.nickName) fields.nickName = '请输入昵称'
    if (input.phonenumber && !/^1[3-9]\d{9}$/.test(input.phonenumber)) fields.phonenumber = '请输入有效的手机号码'
    if (input.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(input.email)) fields.email = '请输入有效的邮箱地址'
    if (Object.keys(fields).length) return
    saving.value = true
    try {
      await updateProfile(input)
      Object.assign(form, input); baseline.value = JSON.stringify(form)
      if (auth.user) auth.user.user.nickName = input.nickName
      notice.value = '个人资料已保存'
    } catch (cause) { error.value = cause instanceof Error ? cause.message : '保存失败，请重试' }
    finally { saving.value = false }
  }
  async function savePassword() {
    if (saving.value) return false
    clearFeedback()
    if (!password.oldPassword) fields.oldPassword = '请输入当前密码'
    if (!password.newPassword) fields.newPassword = '请输入新密码'
    else if (password.newPassword === password.oldPassword) fields.newPassword = '新密码不能与当前密码相同'
    if (!password.confirmPassword) fields.confirmPassword = '请再次输入新密码'
    else if (password.confirmPassword !== password.newPassword) fields.confirmPassword = '两次输入的新密码不一致'
    if (Object.keys(fields).length) return false
    saving.value = true
    try {
      await updatePassword({ oldPassword: password.oldPassword, newPassword: password.newPassword })
      clearPassword()
      return true
    } catch (cause) { error.value = cause instanceof Error ? cause.message : '修改密码失败，请重试'; return false }
    finally { saving.value = false }
  }
  return { loading, saving, ready, error, notice, userName, form, password, dirty, passwordDirty, fields, load, saveProfile, savePassword, clearFeedback, clearPassword }
}
