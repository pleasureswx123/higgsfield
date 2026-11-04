<script setup lang="ts">
import { EditorContent } from '@tiptap/vue-3'
import { ElPopover, ElPagination } from 'element-plus'
import { IconCheck, IconAt } from '@tabler/icons-vue'
import ReferenceThumbnail from '@/components/projects/ReferenceThumbnail.vue'
import ElementEditor from '@/components/projects/ElementEditor.vue'
import Button from '@/components/ui/Button.vue'
import { usePromptReferencePreview } from '@/composables/usePromptReferencePreview'
import type { DraftReference, ModelCapability } from '@/api/creation'
import type { PromptDocument } from '@/utils/promptDocument'
import { usePromptEditor } from '@/composables/usePromptEditor'

const props = defineProps<{
  disabled?: boolean
  references: DraftReference[]
  projectId: string
  model?: ModelCapability | null
  context: string
}>()
const document = defineModel<PromptDocument>({ required: true })
const emit = defineEmits<{
  apply: [value: { prompt: PromptDocument; references: DraftReference[] }]
}>()
const editorState = {
  get document() {
    return document.value
  },
  get references() {
    return props.references
  },
  get projectId() {
    return props.projectId
  },
  get model() {
    return props.model
  },
  get disabled() {
    return props.disabled
  },
  get context() {
    return props.context
  },
}
const { editor, rows, picker, error, visible, anchor, highlighted, select, insert } =
  usePromptEditor(
    () => editorState,
    (value) => emit('apply', value),
  )
const preview = usePromptReferencePreview(
  () => props.projectId,
  () => props.references,
  () => !!props.disabled,
)
defineExpose({ insert })
</script>

<template>
  <div class="composer-rich-prompt" :class="{ disabled }">
    <EditorContent :editor="editor" @mouseover="preview.show" @mouseleave="preview.hide" />
    <ElPopover
      :visible="visible"
      :virtual-ref="anchor"
      virtual-triggering
      placement="top-start"
      :width="300"
      :show-arrow="false"
      popper-class="prompt-element-suggestions"
    >
      <div class="mention-heading">引用素材与项目元素</div>
      <p v-if="picker.loading.value" role="status">正在查找…</p>
      <p v-else-if="picker.error.value" role="alert">{{ picker.error.value }}</p>
      <div v-if="rows.length" role="listbox" aria-label="素材与元素候选">
        <button
          v-for="(row, index) in rows"
          :key="`${row.candidate.kind}:${row.candidate.id}`"
          type="button"
          role="option"
          :aria-selected="index === highlighted"
          :disabled="row.disabled"
          class="mention-option"
          :class="{ active: index === highlighted }"
          @mousedown.prevent
          @click="select(index)"
        >
          <ReferenceThumbnail
            v-if="row.candidate.assetVersionIds.length"
            :version-id="row.candidate.primaryAssetVersionId || row.candidate.assetVersionIds[0]!"
            passive
            allow-original
          />
          <span class="mention-option-copy"
            ><strong>{{ row.candidate.displayName }}</strong
            ><small v-if="row.disabled">当前模型不可用或元素缺图</small></span
          >
          <IconCheck v-if="row.selected" :size="16" class="mention-check" aria-label="已在提示词中引用" />
        </button>
      </div>
      <p v-if="!rows.length && !picker.loading.value && !picker.error.value" role="status">
        没有匹配的项目元素，可使用下方 @ 浏览或创建。
      </p>
      <ElPagination
        v-if="picker.total.value > 12"
        v-model:current-page="picker.page.value"
        :page-size="12"
        :total="picker.total.value"
        layout="prev, pager, next"
        size="small"
      />
    </ElPopover>
    <ElPopover
      :visible="preview.visible.value"
      :virtual-ref="preview.anchor.value"
      virtual-triggering
      placement="top"
      :width="122"
      :show-arrow="false"
      popper-class="prompt-reference-preview"
    >
      <div @mouseenter="preview.keep" @mouseleave="preview.hide">
        <div class="mention-preview-media">
          <ReferenceThumbnail
            v-if="preview.reference.value"
            :version-id="preview.reference.value.assetVersionId"
            passive
            allow-original
            fill
            class="mention-preview-image"
          />
          <strong class="mention-preview-label" :title="`@${preview.label.value}`">@{{ preview.label.value }}</strong>
        </div>
        <Button
          v-if="preview.reference.value && !preview.reference.value.elementRevisionId"
          variant="outline"
          class="mention-preview-save"
          :disabled="disabled || preview.creator.loading.value"
          @click="preview.saveAsElement"
          ><IconAt :size="13" />保存为元素</Button
        >
        <p v-if="preview.error.value || preview.creator.error.value" role="alert">
          {{ preview.error.value || preview.creator.error.value }}
        </p>
      </div>
    </ElPopover>
    <ElementEditor
      v-if="preview.creator.open.value && preview.initialAsset.value"
      visible
      :project-id="projectId"
      :element-id="null"
      :initial-asset="preview.initialAsset.value"
      :actions="preview.creator.actions.value"
      @close="preview.creator.open.value = false"
      @saved="preview.creator.open.value = false"
    />
    <p v-if="error" class="prompt-error" role="alert">{{ error }}</p>
  </div>
</template>

<style scoped>
.composer-rich-prompt {
  width: 100%;
  color: var(--foreground);
}
.composer-rich-prompt.disabled {
  opacity: 0.6;
}
:deep(.tiptap) {
  min-height: 58px;
  max-height: min(280px, 40dvh);
  overflow-y: auto;
  padding: 0 4px;
  border: 0;
  outline: none;
  box-shadow: none;
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
:deep(.tiptap:focus),
:deep(.tiptap:focus-visible) {
  outline: none;
  border: 0;
  box-shadow: none;
}
:deep(.tiptap p) {
  margin: 0;
  padding: 0;
}
:deep(.tiptap p:only-child:has(> br:only-child)::before) {
  content: '描述你想创作的画面，输入 @ 引用元素…';
  color: var(--muted-foreground);
  float: left;
  pointer-events: none;
  height: 0;
}
:deep(.prompt-element-tag) {
  display: inline;
  padding: 2px 6px;
  border-radius: 5px;
  background: color-mix(in srgb, var(--primary) 18%, transparent);
  color: var(--mention-foreground, var(--foreground));
  font-weight: 650;
  box-decoration-break: clone;
  -webkit-box-decoration-break: clone;
}
.mention-heading {
  font-size: 12px;
  color: var(--muted-foreground);
  padding: 4px 0 8px;
}
.mention-option {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 60px;
  width: 100%;
  padding: 8px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--foreground);
  cursor: pointer;
  text-align: left;
}
.mention-option.active,
.mention-option:hover {
  background: var(--surface-hover);
}
.mention-option:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.mention-option small {
  color: var(--muted-foreground);
}
.prompt-error {
  color: var(--el-color-danger);
  font-size: 12px;
  margin: 4px;
}
</style>

<style scoped>
:global(.dark .prompt-element-tag) {
  color: var(--primary);
}
.mention-option :deep(.reference-thumbnail) {
  width: 44px;
  height: 44px;
  flex: 0 0 44px;
  border: 0;
}
.mention-option :deep(img) {
  object-fit: cover;
}
.mention-option-copy {
  flex: 1;
  min-width: 0;
  overflow-wrap: anywhere;
}
.mention-option-copy small {
  display: block;
}
.mention-check {
  color: var(--muted-foreground);
  flex-shrink: 0;
}
[role='listbox'] {
  max-height: 360px;
  overflow-y: auto;
}
.mention-preview-media {
  position: relative;
  width: 100%;
  aspect-ratio: 1;
  overflow: hidden;
  border-radius: 8px;
  background: var(--surface-hover);
  border: 1px solid var(--border);
}
.mention-preview-image :deep(img) { object-fit: cover; }
.mention-preview-label {
  position: absolute;
  inset: auto 0 0;
  padding: 16px 5px 5px;
  color: white;
  background: linear-gradient(transparent, #0009);
  font-size: 12px;
  font-weight: 700;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  pointer-events: none;
}
.mention-preview-save {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
  width: 100%;
  min-height: 26px;
  margin: 6px 0 0;
  padding: 3px 4px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--surface-hover);
  color: var(--foreground);
  font-size: 11px;
  font-weight: 650;
}
.mention-preview-save svg { color: var(--muted-foreground); flex-shrink: 0; }
.mention-preview-save:hover { background: var(--surface-raised); }
</style>

<style>
.prompt-reference-preview.el-popover {
  padding: 6px;
  min-width: 0;
  max-width: calc(100vw - 24px);
  border: 0;
  border-radius: 12px;
  background: var(--surface-raised);
  color: var(--foreground);
  box-shadow: 0 6px 16px #0003;
}
</style>
