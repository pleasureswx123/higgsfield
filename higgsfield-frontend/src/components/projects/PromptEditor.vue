<script setup lang="ts">
import { ElButton, ElInput, ElOption, ElSelect } from 'element-plus'

import { computed, ref } from 'vue'
import type { DraftReference } from '@/api/creation'
import { editPrompt, insertPromptNode, type PromptDocument } from '@/utils/promptDocument'
import Button from '@/components/ui/Button.vue'
const model = defineModel<PromptDocument>({ required: true })
const props = defineProps<{ disabled: boolean; references: DraftReference[] }>()
const active = ref({ block: 0, node: -1 }),
  referenceKey = ref(''),
  error = ref('')
const candidates = computed(() => [...new Set(props.references.map((item) => item.referenceKey))])
function apply(edit: (body: PromptDocument) => void) {
  if (props.disabled) return
  try {
    model.value = editPrompt(model.value, edit)
    error.value = ''
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '提示词修改失败'
  }
}
function text(block: number, index: number, value: string) {
  apply((body) => {
    const node = body.content[block]?.content[index]
    if (node?.type === 'text') node.text = value
  })
}
function toggle(block: number, index: number, mark: 'bold' | 'italic') {
  apply((body) => {
    const node = body.content[block]?.content[index]
    if (node?.type !== 'text') return
    const marks = node.marks || []
    node.marks = marks.some((item) => item.type === mark)
      ? marks.filter((item) => item.type !== mark)
      : [...marks, { type: mark }]
  })
}
function link(block: number, index: number, href: string) {
  apply((body) => {
    if (href) {
      const url = new URL(href)
      if (
        !['http:', 'https:'].includes(url.protocol) ||
        url.username ||
        url.password ||
        /[\s\x00-\x1f]/.test(href)
      )
        throw new Error('链接须为不含账号、密码或空白的HTTP/HTTPS地址')
    }
    const node = body.content[block]?.content[index]
    if (node?.type !== 'text') return
    const marks = (node.marks || []).filter((item) => item.type !== 'link')
    node.marks = href ? [...marks, { type: 'link', href }] : marks
  })
}
function insert(mention: boolean) {
  if (props.disabled || (mention && !candidates.value.includes(referenceKey.value))) return
  try {
    model.value = insertPromptNode(
      model.value,
      active.value.block,
      active.value.node,
      mention
        ? { type: 'mention', referenceKey: referenceKey.value }
        : { type: 'text', text: '', marks: [] },
    )
    active.value = {
      block: Math.min(active.value.block, model.value.content.length - 1),
      node: active.value.node + 1,
    }
    error.value = ''
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '插入失败'
  }
}
function remove(block: number, index: number) {
  apply((body) => {
    body.content[block]?.content.splice(index, 1)
  })
  active.value = { block, node: -1 }
}
function paragraph() {
  apply((body) => {
    body.content.push({ type: 'paragraph', content: [{ type: 'text', text: '', marks: [] }] })
  })
  active.value = { block: model.value.content.length - 1, node: 0 }
}
</script>
<template>
  <div class="prompt-editor">
    <p v-if="error" class="project-error" role="alert">{{ error }}</p>
    <div class="prompt-toolbar">
      <Button type="button" variant="ghost" :disabled="disabled" @click="paragraph">添加段落</Button
      ><Button type="button" variant="ghost" :disabled="disabled" @click="insert(false)"
        >插入文本</Button
      ><el-select
        v-model="referenceKey"
        :disabled="disabled || !candidates.length"
        placeholder="选择已添加的素材引用"
        aria-label="提示词引用"
        ><el-option
          v-for="key in candidates"
          :key="key"
          :label="`引用 ${key}`"
          :value="key" /></el-select
      ><Button
        type="button"
        variant="outline"
        :disabled="disabled || !candidates.includes(referenceKey)"
        @click="insert(true)"
        >插入提及</Button
      >
    </div>
    <p class="muted">先选中文本或引用片段，再在其后插入新片段。普通 @ 文字不会自动变成素材引用。</p>
    <section v-for="(paragraphItem, block) in model.content" :key="block" class="prompt-paragraph">
      <div class="prompt-paragraph-heading">
        <span>段落 {{ block + 1 }}</span
        ><el-button
          text
          :disabled="disabled"
          @click="
            apply((body) => {
              body.content.splice(block, 1)
            })
          "
          >删除段落</el-button
        >
      </div>
      <div
        v-for="(node, index) in paragraphItem.content"
        :key="index"
        class="prompt-node"
        :class="{ active: active.block === block && active.node === index }"
        @click="active = { block, node: index }"
      >
        <template v-if="node.type === 'text'">
          <div class="prompt-tools">
            <el-button
              text
              :disabled="disabled"
              :aria-pressed="node.marks?.some((mark) => mark.type === 'bold') || false"
              @click="toggle(block, index, 'bold')"
              >加粗</el-button
            ><el-button
              text
              :disabled="disabled"
              :aria-pressed="node.marks?.some((mark) => mark.type === 'italic') || false"
              @click="toggle(block, index, 'italic')"
              >斜体</el-button
            ><el-input
              :model-value="node.marks?.find((mark) => mark.type === 'link')?.href || ''"
              :disabled="disabled"
              placeholder="链接（可选）"
              maxlength="2000"
              @change="(value: string) => link(block, index, value)"
            />
          </div>
          <el-input
            :model-value="node.text"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 14 }"
            :disabled="disabled"
            maxlength="20000"
            :aria-label="`段落${block + 1}文本${index + 1}`"
            :class="{
              bold: node.marks?.some((mark) => mark.type === 'bold'),
              italic: node.marks?.some((mark) => mark.type === 'italic'),
            }"
            placeholder="写下场景、主体、动作、光线与镜头想法…"
            @focus="active = { block, node: index }"
            @update:model-value="(value: string) => text(block, index, value)"
          />
        </template>
        <button
          v-else
          type="button"
          class="prompt-mention"
          :disabled="disabled"
          @focus="active = { block, node: index }"
        >
          @ 引用 {{ node.referenceKey }}
        </button>
        <el-button text :disabled="disabled" @click.stop="remove(block, index)">{{
          node.type === 'mention' ? '移除提及' : '移除文本'
        }}</el-button>
      </div>
    </section>
  </div>
</template>
<style scoped>
.prompt-editor {
  width: 100%;
}
.prompt-toolbar,
.prompt-tools,
.prompt-paragraph-heading {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.prompt-toolbar .el-select {
  width: 220px;
}
.prompt-paragraph-heading {
  justify-content: space-between;
  color: var(--muted-foreground);
}
.prompt-paragraph {
  border: 1px solid var(--border);
  padding: 12px;
  border-radius: 12px;
  margin-top: 12px;
  background: var(--surface);
}
.prompt-node {
  border: 1px solid transparent;
  padding: 6px;
  border-radius: 8px;
}
.prompt-node.active {
  border-color: var(--focus);
}
.prompt-tools {
  margin-bottom: 6px;
}
.prompt-tools .el-input {
  flex: 1;
  min-width: 160px;
}
.prompt-mention {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface-hover);
  color: var(--foreground);
  padding: 8px 12px;
}
.prompt-mention:focus-visible {
  outline: 2px solid var(--focus);
}
:deep(.bold textarea) {
  font-weight: 700;
}
:deep(.italic textarea) {
  font-style: italic;
}
</style>
