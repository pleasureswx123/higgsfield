<script setup lang="ts">
import DialogHeading from '@/components/shared/DialogHeading.vue'
import { ElDialog } from 'element-plus'
import { RouterLink } from 'vue-router'
import Button from '@/components/ui/Button.vue'
import {
  useOutputToElement,
  type ElementGenerationDestination,
} from '@/composables/useOutputToElement'
const props = defineProps<{
  outputId: string
  jobId: string
  target: ElementGenerationDestination
}>()
const emit = defineEmits<{ close: [] }>()
const {
  destination,
  active,
  detail,
  asset,
  result,
  loading,
  saving,
  uncertain,
  error,
  locked,
  submit,
} = useOutputToElement(props.outputId, props.jobId, props.target)
function close() {
  if (!locked.value) emit('close')
}
</script>
<template>
  <ElDialog
    :model-value="active"
    title="将归档图片加入目标元素"
    width="min(620px, 94vw)"
    append-to-body
    :before-close="close"
    :show-close="!locked"
    :close-on-press-escape="!locked"
    :close-on-click-modal="false"
  >
    <template #header="{ titleId, titleClass }">
      <DialogHeading :title-id="titleId" :title-class="titleClass" title="将归档图片加入目标元素" />
    </template>
    <p>目标：{{ detail?.element.name || destination.name }} · 元素 {{ destination.id }}</p>
    <p class="muted">
      创建项目素材后追加到元素的图片列表，保留现有主图、字段和属性；无图片时新图成为主图。此操作不重新生成，也不删除原作品。
    </p>
    <p v-if="loading" role="status">正在重新核验作品与目标权限…</p>
    <p v-if="asset && !result" role="status">
      素材
      {{
        asset.id
      }}
      已创建，尚未确认加入元素。重试会复用该素材；现在关闭则可稍后在元素编辑器中从项目素材手动添加。
    </p>
    <p v-if="result" role="status">
      已加入“{{ result.element.name }}”，当前共 {{ result.currentRevision.media.length }} 张图片。
    </p>
    <RouterLink
      v-if="result"
      :to="{
        name: 'project-detail',
        params: { id: destination.projectId },
        query: { tab: 'elements', element: destination.id },
      }"
      >查看目标元素</RouterLink
    >
    <p v-if="error" class="project-error" role="alert">{{ error }}</p>
    <template #footer
      ><Button variant="ghost" :disabled="locked" @click="close">关闭</Button
      ><Button v-if="!result" :disabled="saving || loading" @click="submit">{{
        saving ? '正在加入…' : uncertain ? '重试原请求' : asset ? '重试加入元素' : '确认加入元素'
      }}</Button></template
    >
  </ElDialog>
</template>
