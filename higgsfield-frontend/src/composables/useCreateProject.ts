import { ref, watch, type Ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { createProject } from '@/api/projects'
export function useCreateProject(open: Ref<boolean>, created: (id: string) => void) {
  const form = ref<FormInstance>(),
    name = ref(''),
    pending = ref(false),
    error = ref('')
  let key = '',
    submittedName = ''
  const rules: FormRules = {
    name: [
      {
        validator: (_rule, value, done) => {
          const text = String(value).trim()
          if (!text) return done(new Error('请输入项目名称'))
          if (text.length > 200 || /[\u0000-\u001f]/.test(text))
            return done(new Error('名称最多200个字符，且不能包含控制字符'))
          done()
        },
        trigger: 'blur',
      },
    ],
  }
  watch(open, (value) => {
    if (value) {
      name.value = ''
      error.value = ''
      key = ''
      submittedName = ''
      form.value?.clearValidate()
    }
  })
  async function submit() {
    if (pending.value || !(await form.value?.validate().catch(() => false))) return
    const normalized = name.value.trim()
    // 未知网络结果重试沿用同一幂等键；修改内容后生成新键。
    if (!key || submittedName !== normalized) {
      key = crypto.randomUUID()
      submittedName = normalized
    }
    pending.value = true
    error.value = ''
    try {
      const result = await createProject(normalized, key)
      open.value = false
      created(result.data.id)
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : '创建失败，请重试'
    } finally {
      pending.value = false
    }
  }
  return { form, name, pending, error, rules, submit }
}
