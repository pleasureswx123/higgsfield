<script setup lang="ts">
import DialogHeading from '@/components/shared/DialogHeading.vue'
import { ref } from 'vue'
import { ElDialog, ElPagination } from 'element-plus'
import Button from '@/components/ui/Button.vue'
import { useElementHistory } from '@/composables/useElementHistory'
import type { ElementRevision } from '@/api/elements'
import MediaComments from './MediaComments.vue'
const props = defineProps<{ elementId: string; visible?: boolean }>()
const emit = defineEmits<{ close: [] }>()
const comments = ref<InstanceType<typeof MediaComments>>()
const {
  active,
  rows,
  page,
  total,
  loading,
  error,
  selected,
  selectedVersion,
  preview,
  previewLoading,
  previewError,
  properties,
  choose,
  load,
} = useElementHistory(props.elementId, () => props.visible !== false)
async function mayLeave() {
  return !comments.value || await comments.value.confirmLeave()
}
async function close() { if (await mayLeave()) emit('close') }
async function selectRevision(revision: ElementRevision) {
  if (revision.id === selected.value?.id) return
  if (await mayLeave()) choose(revision)
}
async function selectImage(version: string) {
  if (version === selectedVersion.value) return
  if (await mayLeave()) selectedVersion.value = version
}
async function changePage(value: number) { if (await mayLeave()) page.value = value }
async function refreshHistory() { if (await mayLeave()) await load() }
function propertyText(value: string | string[] | null) {
  return Array.isArray(value) ? value.join('、') : value || '未填写'
}
</script>
<template>
  <ElDialog
    :model-value="active"
    title="历史修订"
    width="min(1100px, 96vw)"
    append-to-body
    :before-close="close"
    :close-on-click-modal="false"
  >
    <template #header="{ titleId, titleClass }">
      <DialogHeading :title-id="titleId" :title-class="titleClass" title="历史修订" />
    </template>
    <p class="muted">
      描述、属性与媒体固定在各次修订；此处查看不会替换当前编辑内容。展示标签可独立于内部修订更新。
    </p>
    <p v-if="error" class="project-error" role="alert">{{ error }}</p>
    <p v-if="loading" role="status">正在加载历史修订…</p>
    <div class="element-history-layout">
      <aside class="element-history-list">
        <button
          v-for="revision in rows"
          :key="revision.id"
          class="element-copy-project"
          :class="{ active: selected?.id === revision.id }"
          :aria-pressed="selected?.id === revision.id"
          @click="selectRevision(revision)"
        >
          <strong>修订 #{{ revision.revisionNo }}</strong
          ><small
            >{{ revision.label || '无展示标签' }} · {{ revision.media.length }} 张图</small
          ></button
        ><ElPagination
          v-if="total > 30"
          :current-page="page"
          @current-change="changePage"
          :page-size="30"
          :total="total"
          layout="prev, next"
        />
      </aside>
      <section v-if="selected" class="element-history-content">
        <div class="element-history-image">
          <img v-if="preview" :src="preview" :alt="'修订 ' + selected.revisionNo + ' 图片'" />
          <p v-else-if="previewLoading" role="status">正在授权读取历史图片…</p>
          <p v-else-if="previewError" class="project-error" role="alert">{{ previewError }}</p>
          <p v-else class="muted">此修订无图片</p>
        </div>
        <div class="element-media-strip">
          <button
            v-for="(media, index) in selected.media"
            :key="media.assetVersionId"
            :class="{ active: selectedVersion === media.assetVersionId }"
            @click="selectImage(media.assetVersionId)"
          >
            图片 {{ index + 1 }}{{ media.isPrimary ? ' · 主图' : '' }}
          </button>
        </div>
        <h4>描述</h4>
        <p class="element-history-description">{{ selected.description || '未填写' }}</p>
        <h4 v-if="properties.length">属性快照</h4>
        <dl class="element-history-properties">
          <template v-for="property in properties" :key="property.definitionId"
            ><dt>
              {{ property.name }} <small class="muted">v{{ property.definitionVersion }}</small>
            </dt>
            <dd>{{ propertyText(property.value) }}</dd></template
          >
        </dl>
        <MediaComments v-if="selectedVersion" :visible="active" ref="comments" :target="{ assetVersionId: selectedVersion }" media-kind="image" />
      </section>
    </div>
    <template #footer
      ><Button variant="ghost" :disabled="loading" @click="refreshHistory">刷新</Button
      ><Button @click="close">关闭</Button></template
    >
  </ElDialog>
</template>
