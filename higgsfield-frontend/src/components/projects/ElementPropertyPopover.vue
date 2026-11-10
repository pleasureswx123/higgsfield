<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { ElForm, ElFormItem, ElInput, type FormRules } from 'element-plus'
import { IconPlus, IconLetterT, IconPencil } from '@tabler/icons-vue'
import Button from '@/components/ui/Button.vue'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { usePropertyDefinitions } from '@/composables/usePropertyDefinitions'
import type { PropertyDefinition } from '@/api/elements'

const props = defineProps<{ projectId: string; visible: boolean; disabled: boolean; definition?: PropertyDefinition; attachedDefinitions?: PropertyDefinition[] }>()
const emit = defineEmits<{ changed: [definition: PropertyDefinition]; busy: [value: boolean] }>()
const open = ref(false)
const host = ref<HTMLElement>()
const portalTo = ref<HTMLElement>()
onMounted(() => { portalTo.value = host.value?.closest<HTMLElement>('.el-dialog') || undefined })
let saved = false
const { fields, form, saving, locked, editable, uncertain, error, edit, save } = usePropertyDefinitions(
  props.projectId,
  definition => { saved = true; emit('changed', definition) },
  () => props.visible,
  false,
  () => props.attachedDefinitions || [],
)
const rules: FormRules = {
  name: [{ required: true, whitespace: true, message: '请输入属性名称', trigger: 'blur' }],
}
async function updateOpen(value: boolean) {
  if (value && props.definition && !open.value && !locked.value) await edit(props.definition)
  if (!locked.value) open.value = value
}
async function add() {
  if (props.disabled) return
  if (!uncertain.value && !props.definition) {
    fields.valueType = 'text'
    fields.optionsText = ''
  }
  saved = false
  await save()
  if (saved) {
    open.value = false
    await edit()
  }
}
watch(() => props.visible, value => { if (!value) open.value = false })
watch([open, locked], ([opened, busy]) => emit('busy', opened || busy))
defineExpose({ locked, open })
</script>

<template>
  <span ref="host" :class="definition ? 'element-property-edit' : 'element-property-entry'">
  <Popover :open="open && visible" @update:open="updateOpen">
    <PopoverTrigger as-child>
      <Button type="button" variant="ghost" :class="definition ? 'element-property-icon' : 'element-add-property'" :aria-label="definition ? `编辑属性 ${definition.name}` : undefined" :disabled="disabled || !editable">
        <IconPencil v-if="definition" :size="16" />
        <template v-else><IconPlus :size="18" />添加自定义属性</template>
      </Button>
    </PopoverTrigger>
    <PopoverContent :portal-to="portalTo" class="element-property-popover" :class="{ 'element-property-popover--edit': definition }" align="end" side="top" :side-offset="6" :collision-padding="12" :aria-label="definition ? '编辑属性名称' : '添加文本属性'"
      @escape-key-down="locked && $event.preventDefault()" @interact-outside="locked && $event.preventDefault()">
      <h3>文本属性名称</h3>
      <ElForm ref="form" :model="fields" :rules="rules" label-position="top" :disabled="locked || disabled || !editable" @submit.prevent.stop="add">
        <ElFormItem prop="name"><ElInput v-model="fields.name" aria-label="属性名称" maxlength="200" placeholder="属性名称"><template #prefix><IconLetterT :size="18" /></template></ElInput></ElFormItem>
        <p v-if="error" class="property-error" role="alert">{{ error }}</p>
        <p v-if="uncertain && !saving" class="property-hint" role="status">保存结果待确认，请重试确认。</p>
        <div class="property-footer">
          <Button type="button" variant="ghost" :disabled="locked" @click="updateOpen(false)">取消</Button>
          <Button type="submit" :disabled="saving || disabled || !editable || (!uncertain && !fields.name.trim())">{{ saving ? '保存中…' : uncertain ? '重试确认' : '保存' }}</Button>
        </div>
      </ElForm>
    </PopoverContent>
  </Popover>
  </span>
</template>

<style>
.element-property-popover { --property-surface: #f4f5f2; --property-input: #e3e5e1; --property-line: #cdd0c9; --property-muted: #777b74; --property-cancel: #e0e3dc; --property-save: #858b80; --property-save-text: #fff; z-index: 4000; width: calc(var(--reka-popover-trigger-width) - 32px); min-width: 240px; max-width: calc(100vw - 24px); max-height: var(--reka-popover-content-available-height); overflow-y: auto; padding: 14px; border: 1px solid var(--property-line); border-radius: 14px; background: var(--property-surface); color: var(--foreground); box-shadow: 0 4px 12px #0000000a; }
.dark .element-property-popover { --property-surface: #26292b; --property-input: #3a3d3f; --property-line: #484b4d; --property-muted: #727575; --property-cancel: #383c3e; --property-save: #939596; --property-save-text: #171819; border-color: #35383a; }
.element-property-popover h3 { margin: 0 0 8px; font-size: 13px; line-height: 18px; font-weight: 400; color: var(--property-muted); }
.element-property-popover--edit { width: 280px; }
.element-property-popover .property-hint { margin: 6px 0 14px; color: var(--muted-foreground); font-size: 12px; line-height: 18px; }
.element-property-popover .el-form-item { margin-bottom: 12px; }
.element-property-popover .el-form-item__label { font-size: 12px; line-height: 18px; margin-bottom: 4px; padding: 0; }
.element-property-popover .el-input__wrapper { min-height: 40px; padding: 0 12px; border-radius: 13px; background: var(--property-input); box-shadow: inset 0 0 0 1px var(--property-line); }
.element-property-popover .el-input__wrapper.is-focus { box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--property-line) 70%, var(--foreground)); }
.element-property-popover .el-input__prefix, .element-property-popover .el-input__inner::placeholder { color: var(--property-muted); }
.element-property-popover .el-input__inner { font-size: 14px; }
.element-property-popover .property-footer { display: flex; gap: 8px; margin-top: 12px; }
.element-property-popover .property-footer .ui-button { flex: 1; height: 26px; min-height: 26px; padding: 0 10px; border: 0; border-radius: 6px; font-size: 12px; line-height: 18px; box-shadow: none; background: var(--property-cancel); color: var(--foreground); }
.element-property-popover .property-footer .ui-button[type='submit'] { background: var(--property-save); color: var(--property-save-text); }
.element-property-popover .property-footer .ui-button:disabled { opacity: 1; cursor: not-allowed; }
.element-property-popover .property-footer .ui-button:not(:disabled):hover { filter: brightness(1.08); }
.element-property-popover .property-error { color: var(--el-color-danger); font-size: 12px; line-height: 18px; overflow-wrap: anywhere; }
</style>
