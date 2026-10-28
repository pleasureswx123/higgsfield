<script setup lang="ts">
import {
  ElDialog,
  ElForm,
  ElFormItem,
  ElInput,
  ElSelect,
  ElOption,
  ElPagination,
  type FormRules,
} from 'element-plus'
import Button from '@/components/ui/Button.vue'
import DialogHeading from '@/components/shared/DialogHeading.vue'
import { usePropertyDefinitions } from '@/composables/usePropertyDefinitions'
import type { PropertyDefinition } from '@/api/elements'
const props = defineProps<{ projectId: string; visible?: boolean }>()
const emit = defineEmits<{ close: []; changed: [definition: PropertyDefinition] }>()
const {
  active,
  valid,
  rows,
  page,
  total,
  loading,
  saving,
  locked,
  editable,
  uncertain,
  error,
  notice,
  editing,
  form,
  fields,
  dirty,
  load,
  edit,
  save,
  confirmDiscard,
} = usePropertyDefinitions(props.projectId, (definition) => emit('changed', definition), () => props.visible !== false)
const rules: FormRules = {
  name: [{ required: true, whitespace: true, message: '请输入属性名称', trigger: 'blur' }],
  propertyKey: [
    {
      required: true,
      pattern: /^[a-z][a-z0-9_]*$/,
      message: '使用小写字母开头，可含数字和下划线',
      trigger: 'blur',
    },
  ],
  optionsText: [
    {
      validator: (_rule, value: string, callback) => {
        if (fields.valueType === 'text') return callback()
        const options = value
          .split('\n')
          .map((option) => option.trim())
          .filter(Boolean)
        if (!options.length) callback(new Error('至少填写一个选项，每行一个'))
        else if (new Set(options).size !== options.length) callback(new Error('选项不能重复'))
        else callback()
      },
      trigger: 'blur',
    },
  ],
}
async function close() {
  if (await confirmDiscard()) emit('close')
}
</script>
<template>
  <ElDialog
    :model-value="visible !== false && (active || !valid)"
    title="项目元素属性"
    width="min(820px, 94vw)"
    append-to-body
    :before-close="close"
    :show-close="!locked"
    :close-on-click-modal="false"
  >
    <template #header="{ titleId, titleClass }">
      <DialogHeading :title-id="titleId" :title-class="titleClass" title="项目元素属性" />
    </template>
    <p class="muted">定义更新会生成新版本，不覆盖已有元素修订中的属性快照。</p>
    <div class="property-settings-layout">
      <aside>
        <div class="element-toolbar">
          <Button variant="outline" :disabled="locked || !editable" @click="edit()">新增属性</Button
          ><Button variant="ghost" :disabled="loading || locked || !editable" @click="load"
            >刷新</Button
          >
        </div>
        <p v-if="loading" role="status">加载中…</p>
        <button
          v-for="definition in rows"
          :key="definition.id"
          class="element-copy-project"
          :class="{ active: editing?.propertyKey === definition.propertyKey }"
          :disabled="locked || !editable"
          @click="edit(definition)"
        >
          <strong>{{ definition.name }}</strong
          ><small class="muted"
            >{{
              definition.valueType === 'text'
                ? '文本'
                : definition.valueType === 'multi_select'
                  ? '多选'
                  : '历史单选'
            }}
            · 版本 {{ definition.versionNo }}</small
          >
        </button>
        <p v-if="!loading && !rows.length" class="muted">尚未配置属性</p>
        <ElPagination
          v-if="total > 100"
          v-model:current-page="page"
          :page-size="100"
          :total="total"
          :disabled="locked || !editable"
          layout="prev, next"
        />
      </aside>
      <section>
        <h3>{{ editing ? '创建定义新版本' : '新增属性' }}</h3>
        <ElForm
          ref="form"
          :model="fields"
          :rules="rules"
          label-position="top"
          :disabled="locked || !editable"
          ><ElFormItem label="属性名称" prop="name"
            ><ElInput v-model="fields.name" maxlength="200" /></ElFormItem
          ><ElFormItem label="稳定属性标识" prop="propertyKey"
            ><ElInput
              v-model="fields.propertyKey"
              maxlength="100"
              :disabled="Boolean(editing)"
            /><small class="muted">用于识别同一属性，创建后保持不变。</small></ElFormItem
          ><ElFormItem label="属性类型"
            ><ElSelect v-model="fields.valueType"
              ><ElOption label="文本" value="text" /><ElOption
                label="多选"
                value="multi_select" /></ElSelect></ElFormItem
          ><ElFormItem
            v-if="fields.valueType === 'multi_select'"
            label="可选值（每行一个）"
            prop="optionsText"
            ><ElInput
              v-model="fields.optionsText"
              type="textarea"
              :rows="6"
              placeholder="红色&#10;蓝色" /></ElFormItem
        ></ElForm>
        <p v-if="editing?.valueType === 'single_select'" class="muted">
          历史单选仍保留；新版本可选择文本或多选。
        </p>
        <p v-if="editing" class="muted">
          当前基准：版本 {{ editing.versionNo }}。若他人已更新，请刷新列表并重新选择。
        </p>
      </section>
    </div>
    <p v-if="uncertain" role="status">
      保存结果尚未确认，请使用原请求重试；确认前暂不能编辑或关闭。
    </p>
    <p v-if="error" class="project-error" role="alert">{{ error }}</p>
    <p v-if="notice" role="status">{{ notice }}</p>
    <template #footer
      ><span v-if="dirty" class="muted">有未保存配置</span
      ><Button variant="ghost" :disabled="locked" @click="close">关闭</Button
      ><Button
        :disabled="saving || !editable || (!uncertain && Boolean(editing) && !dirty)"
        @click="save"
        >{{
          saving ? '保存中…' : uncertain ? '重试确认原请求' : editing ? '保存为新版本' : '创建属性'
        }}</Button
      ></template
    >
  </ElDialog>
</template>
