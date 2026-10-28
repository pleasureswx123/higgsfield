<script setup lang="ts">
import { ElInput } from 'element-plus'
import { IconBold, IconItalic, IconPlus, IconTrash } from '@tabler/icons-vue'
import type { BriefBody, TextMark } from '@/api/projectWorkspace'
import Button from '@/components/ui/Button.vue'
const model = defineModel<BriefBody>({ required: true })
defineProps<{ disabled: boolean }>()
function update(block: number, node: number, field: 'text' | 'marks', value: string | TextMark[]) {
  const body: BriefBody = JSON.parse(JSON.stringify(model.value))
  const target = body.content[block]?.content[node]
  if (!target) return
  if (field === 'text') target.text = value as string
  else target.marks = value as TextMark[]
  model.value = body
}
function toggle(block: number, node: number, type: 'bold' | 'italic') {
  const marks = model.value.content[block]!.content[node]!.marks
  update(
    block,
    node,
    'marks',
    marks.some((m) => m.type === type)
      ? marks.filter((m) => m.type !== type)
      : [...marks, { type }],
  )
}
function link(block: number, node: number, href: string) {
  const marks = model.value.content[block]!.content[node]!.marks.filter((m) => m.type !== 'link')
  update(block, node, 'marks', href ? [...marks, { type: 'link', href }] : marks)
}
function add() {
  model.value = {
    ...model.value,
    content: [
      ...model.value.content,
      { type: 'paragraph', content: [{ type: 'text', text: '', marks: [] }] },
    ],
  }
}
function remove(index: number) {
  model.value = { ...model.value, content: model.value.content.filter((_, i) => i !== index) }
}
</script>
<template>
  <div class="brief-editor">
    <p v-if="!model.content.length" class="muted">记录项目目标、故事方向、视觉风格与制作安排。</p>
    <section v-for="(paragraph, index) in model.content" :key="index" class="brief-paragraph">
      <div class="brief-paragraph-top">
        <span>段落 {{ index + 1 }}</span
        ><Button
          variant="ghost"
          :disabled="disabled"
          :aria-label="`删除段落 ${index + 1}`"
          @click="remove(index)"
          ><IconTrash :size="16"
        /></Button>
      </div>
      <div v-for="(node, n) in paragraph.content" :key="n" class="brief-text-block">
        <div class="brief-tools">
          <Button
            variant="ghost"
            aria-label="加粗"
            :aria-pressed="node.marks.some((m) => m.type === 'bold')"
            :disabled="disabled"
            @click="toggle(index, n, 'bold')"
            ><IconBold :size="17"
          /></Button>
          <Button
            variant="ghost"
            aria-label="斜体"
            :aria-pressed="node.marks.some((m) => m.type === 'italic')"
            :disabled="disabled"
            @click="toggle(index, n, 'italic')"
            ><IconItalic :size="17"
          /></Button>
          <ElInput
            :model-value="node.marks.find((m) => m.type === 'link')?.href || ''"
            placeholder="链接（可选，https://…）"
            :aria-label="`段落 ${index + 1} 链接`"
            :disabled="disabled"
            maxlength="2000"
            @update:model-value="link(index, n, $event)"
          />
        </div>
        <ElInput
          :model-value="node.text"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 16 }"
          :aria-label="`段落 ${index + 1} 正文`"
          placeholder="写下你的项目简报…"
          :disabled="disabled"
          maxlength="20000"
          :class="{
            'text-bold': node.marks.some((m) => m.type === 'bold'),
            'text-italic': node.marks.some((m) => m.type === 'italic'),
          }"
          @update:model-value="update(index, n, 'text', $event)"
        />
      </div>
    </section>
    <Button variant="outline" :disabled="disabled || model.content.length >= 200" @click="add"
      ><IconPlus :size="17" />添加段落</Button
    >
  </div>
</template>
