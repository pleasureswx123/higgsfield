<script setup lang="ts">
import { ElButton, ElPopover, ElInput, ElOption, ElPagination, ElSelect, ElMessageBox } from 'element-plus'

import { reactive, shallowRef, watch } from 'vue'
import type { DraftReference, ModelCapability } from '@/api/creation'
import type { ReferenceCandidate } from '@/api/references'
import { useReferencePicker } from '@/composables/useReferencePicker'
import { useReferenceUpdates } from '@/composables/useReferenceUpdates'
import { appendCandidate, moveReference, compatibleReferenceRoles, selectReferenceMedia } from '@/utils/draftReferences'
import ReferenceUploads from './ReferenceUploads.vue'
import ReferenceThumbnail from './ReferenceThumbnail.vue'
import Button from '@/components/ui/Button.vue'
const props = defineProps<{
  projectId: string
  folderId?: string | null
  disabled: boolean
  protectedKeys: string[]
  model?: ModelCapability | null
}>()
const emit = defineEmits<{ uploaded: [] }>()
const references = defineModel<DraftReference[]>({ required: true })
const revisionUpdates = useReferenceUpdates(() => props.projectId, references, () => props.disabled, () => props.model)
const firstForKey = (index: number) => references.value.findIndex(item => item.referenceKey === references.value[index]?.referenceKey) === index
function upgrade(key: string) {
  void revisionUpdates.upgrade(key, message => ElMessageBox.confirm(message, '确认升级元素引用', {
    confirmButtonText: '替换为新修订图片', cancelButtonText: '保留原引用', type: 'warning',
  }).then(() => true).catch(() => false))
}
const { open, q, kind, rows, page, total, loading, error, load, search, show: openPicker, close, canSelect, contextRevision } =
  useReferencePicker(() => props.projectId, () => props.disabled)
const roles = reactive<Record<string, string>>({})
const mediaSelections = reactive<Record<string, string[]>>({})
watch(contextRevision, () => {
  for (const key of Object.keys(roles)) delete roles[key]
  for (const key of Object.keys(mediaSelections)) delete mediaSelections[key]
}, { flush: 'sync' })
const mediaIdentity = (row: ReferenceCandidate) => `${identity(row)}:${row.elementRevisionId}`
const selectedMedia = (row: ReferenceCandidate) => mediaSelections[mediaIdentity(row)] ?? [row.primaryAssetVersionId || row.assetVersionIds[0]!]
function toggleMedia(row: ReferenceCandidate, id: string, checked: boolean) {
  if (props.disabled) return
  const chosen = selectedMedia(row).filter(value => value !== id)
  mediaSelections[mediaIdentity(row)] = checked ? [...chosen, id] : chosen
}
const labels: Record<string, string> = {
  reference_image: '参考图',
  first_frame: '首帧',
  reference_video: '参考视频',
}
const identity = (row: ReferenceCandidate) => `${row.kind}:${row.id}`
const options = (row: ReferenceCandidate) => compatibleReferenceRoles(row, props.model)
function selectedRole(row: ReferenceCandidate) {
  const available = options(row)
  return available.includes(roles[identity(row)] || '') ? roles[identity(row)] : available[0]
}
function uploaded() {
  emit('uploaded')
  if (!open.value || props.disabled) return
  kind.value = 'asset'
  q.value = ''
  search()
}
function add(row: ReferenceCandidate) {
  if (!canSelect(row)) return
  const role = selectedRole(row)
  if (!role || !options(row).includes(role)) return
  try {
    const candidate = role === 'reference_image' ? selectReferenceMedia(row, selectedMedia(row)) : row
    references.value = appendCandidate(references.value, candidate, role, props.model)
    error.value = ''
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '添加引用失败'
  }
}
function remove(index: number) {
  const item = references.value[index]
  if (!item || props.disabled || props.protectedKeys.includes(item.referenceKey)) return
  references.value = references.value
    .filter((_, position) => position !== index)
    .map((value, ordinal) => ({ ...value, ordinal }))
}
function move(index: number, offset: number) {
  if (!props.disabled) references.value = moveReference(references.value, index, offset)
}
const anchor = shallowRef<HTMLElement>()
function show(source?: 'asset' | 'element', target?: HTMLElement) {
  if (target) anchor.value = target
  if (open.value && kind.value === source) { close(); return }
  openPicker(source)
}
function switchTab(source: 'asset' | 'element') {
  kind.value = source
  search()
}
defineExpose({ show })
</script>

<template>
  <section class="draft-references">
    <div class="reference-heading">
      <h3>
        参考素材 <span>{{ references.length }}/200</span>
      </h3>
      <Button type="button" variant="outline" :disabled="disabled" @click="show('asset', $event.currentTarget as HTMLElement)"
        >添加素材 / 元素</Button
      >
    </div>
    <p v-if="!references.length" class="muted">
      可选择项目内有引用权限的素材或元素；保存后固定为当前版本。
    </p>
    <p v-if="revisionUpdates.loading.value" class="muted">正在检查元素修订，当前引用保持不变…</p>
    <p v-if="revisionUpdates.error.value" role="alert">{{ revisionUpdates.error.value }}</p>
    <Button v-if="references.some(item => item.elementRevisionId)" variant="ghost" :disabled="disabled || revisionUpdates.loading.value" @click="revisionUpdates.check">检查元素更新</Button>
    <ul>
      <li
        v-for="(item, index) in references"
        :key="`${item.referenceKey}:${item.assetVersionId}:${item.mediaRole}`"
      >
        <ReferenceThumbnail
          v-if="['reference_image', 'first_frame'].includes(item.mediaRole)"
          :version-id="item.assetVersionId"
        />
        <span
          >{{ index + 1 }} · {{ labels[item.mediaRole] || item.mediaRole }} · 素材版本
          {{ item.assetVersionId
          }}<small v-if="item.elementRevisionId">
            · 元素修订 {{ item.elementRevisionId }}</small
          ></span
        >
        <div v-if="item.elementRevisionId && firstForKey(index) && revisionUpdates.updates.value[item.elementRevisionId]?.state === 'updated'" class="reference-upgrade">
          <p>元素已有新修订 {{ revisionUpdates.updates.value[item.elementRevisionId]?.candidate?.elementRevisionId }}，当前仍使用旧修订。</p>
          <ReferenceThumbnail v-for="id in revisionUpdates.updates.value[item.elementRevisionId]?.candidate?.assetVersionIds" :key="id" :version-id="id" />
          <Button variant="ghost" :disabled="disabled" @click="upgrade(item.referenceKey)">检查并升级此引用</Button>
        </div>
        <p v-if="item.elementRevisionId && firstForKey(index) && revisionUpdates.updates.value[item.elementRevisionId]?.state === 'unavailable'" class="muted">无法确认此元素的新修订是否可用，旧引用保留；保存及提交时仍会重新校验权限。</p>
        <div>
          <el-button text :disabled="disabled || index === 0" @click="move(index, -1)"
            >上移</el-button
          ><el-button
            text
            :disabled="disabled || index === references.length - 1"
            @click="move(index, 1)"
            >下移</el-button
          ><el-button
            text
            :disabled="disabled || protectedKeys.includes(item.referenceKey)"
            :title="
              protectedKeys.includes(item.referenceKey)
                ? '提示词仍提及此引用，请先编辑提示词'
                : '移除引用'
            "
            @click="remove(index)"
            >移除</el-button
          >
        </div>
      </li>
    </ul>
    <ElPopover :visible="open" :virtual-ref="anchor" virtual-triggering placement="top-start" :width="800" :show-arrow="false" popper-class="creation-reference-popover" :popper-options="{ modifiers: [{ name: 'flip', options: { fallbackPlacements: ['bottom-start', 'top-end'] } }] }">
      <section class="reference-picker-panel" role="dialog" aria-label="选择参考素材" @keydown.esc.stop="close">
      <header class="reference-picker-tabs">
        <button type="button" :aria-pressed="kind !== 'element'" @click="switchTab('asset')">素材</button>
        <button type="button" :aria-pressed="kind === 'element'" @click="switchTab('element')">元素</button>
        <button type="button" class="reference-picker-close" aria-label="关闭素材面板" @click="close">×</button>
      </header>
      <div class="reference-picker-content">
      <ReferenceUploads v-show="kind !== 'element'" :project-id="projectId" :folder-id="folderId ?? null" :disabled="disabled || !open" @uploaded="uploaded" />
      <div class="reference-search">
        <el-input
          v-model="q"
          placeholder="搜索素材或元素名称"
          clearable
          @keyup.enter="search"
          @clear="search"
        /><Button type="button" variant="outline" :disabled="loading" @click="search">查询</Button>
      </div>
      <p v-if="error" class="project-error" role="alert">{{ error }}</p>
      <p v-if="loading" role="status">正在读取可引用内容…</p>
      <ul v-else class="reference-candidates">
        <li v-for="row in rows" :key="identity(row)">
          <div>
            <ReferenceThumbnail v-if="row.primaryAssetVersionId || row.assetVersionIds[0]" :version-id="row.primaryAssetVersionId || row.assetVersionIds[0]!" />
            <strong>{{ row.displayName }}</strong>
            <p class="muted">
              {{ row.kind === 'element' ? '元素' : '素材' }} ·
              {{ row.assetVersionIds.length }} 个固定素材版本
            </p>
            <div v-if="row.kind === 'element' && selectedRole(row) === 'reference_image'" class="reference-media-options">
              <label v-for="id in row.assetVersionIds" :key="id">
                <input type="checkbox" :checked="selectedMedia(row).includes(id)" :disabled="disabled"
                  :aria-label="`选择素材版本 ${id}`" @change="toggleMedia(row, id, ($event.target as HTMLInputElement).checked)" />
                <ReferenceThumbnail :version-id="id" />
                <span>{{ id === row.primaryAssetVersionId ? '主图 · ' : '' }}版本 {{ id }}</span>
              </label>
            </div>
          </div>
          <el-select
            :model-value="selectedRole(row)"
            :disabled="!options(row).length"
            @update:model-value="(value: string) => (roles[identity(row)] = value)"
            ><el-option
              v-for="role in options(row)"
              :key="role"
              :label="labels[role] || role"
              :value="role" /></el-select
          ><Button type="button" :disabled="disabled || !options(row).length" @click="add(row)"
            >加入</Button
          >
        </li>
      </ul>
      <p v-if="!loading && !rows.length" class="muted">暂无可引用的匹配内容。</p>
      <p class="muted">
        元素参考图默认选择主图，可勾选多张图片；首帧仅加入主图。已选模型时会先校验角色与数量；生成预检仍会再次校验。
      </p>
      <el-pagination
        v-if="total > 12"
        v-model:current-page="page"
        :page-size="12"
        :total="total"
        layout="prev,pager,next"
        @current-change="load"
      />
      </div>
      </section>
    </ElPopover>
  </section>
</template>
<style>
.creation-reference-popover.el-popover { padding:0; max-width:calc(100vw - 24px); border-radius:16px; background:var(--surface); color:var(--foreground); border:1px solid var(--border); box-shadow:0 16px 48px #0005; }
</style>
<style scoped>
.reference-picker-panel { max-height:min(580px, 70vh); display:flex; flex-direction:column; }
.reference-picker-tabs { display:flex; gap:8px; padding:14px 18px; border-bottom:1px solid var(--border); }
.reference-picker-tabs button { padding:8px 16px; border:0; border-radius:8px; background:transparent; color:var(--muted-foreground); cursor:pointer; }
.reference-picker-tabs button[aria-pressed="true"] { color:var(--foreground); background:var(--surface-hover); }
.reference-picker-tabs .reference-picker-close { margin-left:auto; font-size:20px; padding:3px 10px; }
.reference-picker-content { overflow:auto; padding:18px; min-height:280px; }
.reference-picker-content .reference-search { margin:14px 0; }
.reference-candidates { display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:12px; }
.reference-candidates li { flex-wrap:wrap; padding:12px; border:1px solid var(--border); border-radius:12px; align-content:start; }
.reference-candidates li > div:first-child { flex-basis:100%; }
.reference-candidates strong { display:block; margin-top:8px; }

.draft-references {
  margin: 16px 0;
  border-top: 1px solid var(--border);
  padding-top: 16px;
}
.reference-heading,
.reference-search {
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: space-between;
}
.reference-heading h3 {
  font-size: 14px;
}
.reference-upgrade {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--muted);
}
.reference-media-options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.reference-media-options label {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 12px;
  overflow-wrap: anywhere;
}
.reference-media-options input { accent-color: var(--primary); }
.reference-upgrade p {
  width: 100%;
  margin: 0;
  overflow-wrap: anywhere;
}
.reference-heading span {
  color: var(--muted-foreground);
}
ul {
  list-style: none;
  padding: 0;
}
li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
}
.reference-search .el-select {
  width: 120px;
  flex-shrink: 0;
}
.reference-search > button {
  flex-shrink: 0;
  white-space: nowrap;
}
.reference-candidates .el-select {
  width: 130px;
  flex-shrink: 0;
}
.reference-candidates li > div:first-child {
  flex: 1 0 100%;
  min-width: 0;
  overflow-wrap: anywhere;
}
@media (max-width: 600px) {
  li {
    flex-wrap: wrap;
  }
  .reference-search {
    flex-wrap: wrap;
  }
}
</style>
