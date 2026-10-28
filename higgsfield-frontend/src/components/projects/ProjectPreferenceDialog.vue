<script setup lang="ts">
import DialogHeading from '@/components/shared/DialogHeading.vue'
import { ElDialog, ElForm, ElFormItem, ElCheckbox, ElSelect, ElOption, ElInputNumber, ElAlert } from 'element-plus'
import Button from '@/components/ui/Button.vue'
import { useProjectPreferenceEditor } from '@/composables/useProjectPreferenceEditor'
const emit = defineEmits<{ changed: [] }>()
const { open, target, form, fields, rules, collections, loading, saving, uncertain, locked, ready, error, start, close, load, save } = useProjectPreferenceEditor(() => emit('changed'))
defineExpose({ start })
</script>
<template>
  <ElDialog :model-value="open" title="个人项目偏好" width="480px" align-center :close-on-click-modal="false"
    :close-on-press-escape="!locked" :show-close="!locked" :before-close="() => close()">
    <template #header="{ titleId, titleClass }">
      <DialogHeading :title-id="titleId" :title-class="titleClass" title="个人项目偏好" />
    </template>
    <p>{{ target?.name }}</p>
    <ElAlert v-if="error" :title="error" type="error" :closable="false" />
    <ElAlert v-if="uncertain && !saving" title="保存结果尚未确认。请重试同一请求，确认前不能更改内容或离开。" type="warning" :closable="false" />
    <p v-if="loading" role="status">正在加载个人偏好…</p>
    <ElForm v-else ref="form" :model="fields" :rules="rules" label-position="top" :disabled="locked || !ready">
      <ElFormItem label="个人导航"><ElCheckbox v-model="fields.isPinned">置顶</ElCheckbox><ElCheckbox v-model="fields.isHidden">隐藏</ElCheckbox></ElFormItem>
      <ElFormItem label="个人集合"><ElSelect v-model="fields.collectionId" placeholder="未分组" clearable :value-on-clear="null">
        <ElOption v-for="item in collections" :key="item.id" :value="item.id" :label="item.name" />
      </ElSelect></ElFormItem>
      <ElFormItem label="个人排序（数值越小越靠前）" prop="orderNum"><ElInputNumber v-model="fields.orderNum" :precision="0" :min="-2147483648" :max="2147483647" /></ElFormItem>
      <p class="muted">这些设置仅影响你的项目列表，不改变项目状态或成员权限。</p>
    </ElForm>
    <template #footer>
      <Button variant="ghost" :disabled="locked" @click="close">取消</Button>
      <Button v-if="!ready && !locked" variant="outline" :disabled="loading" @click="load">重新加载</Button>
      <Button :disabled="saving || loading || !ready" @click="save">{{ saving ? '正在保存…' : uncertain ? '重试同一请求' : '保存偏好' }}</Button>
    </template>
  </ElDialog>
</template>
