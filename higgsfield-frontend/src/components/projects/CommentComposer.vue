<script setup lang="ts">
import { computed, ref, nextTick } from 'vue'
import {
  IconMoodSmile,
  IconAt,
  IconArrowUp,
  IconX,
  IconBrush,
  IconPencil,
  IconCheck,
} from '@tabler/icons-vue'
import CommentEmojiPicker from './CommentEmojiPicker.vue'
const props = defineProps<{
  disabled?: boolean
  blocked?: boolean
  floating?: boolean
  editing?: boolean
  drawing?: boolean
  members?: { userId: string; displayName: string }[]
  color?: string
  tool?: 'path' | 'point'
  annotation?: boolean
}>()
const body = defineModel<string>({ required: true })
const emit = defineEmits<{
  send: []
  cancel: []
  drawing: []
  color: [value: string]
  tool: [value: 'path' | 'point']
}>()
const emojiOpen = ref(false),
  input = ref<HTMLTextAreaElement>()
const mention = computed(() => /(?:^|\s)@([^\s@]*)$/.exec(body.value))
const matches = computed(() =>
  (props.members || [])
    .filter((item) =>
      item.displayName.toLowerCase().includes((mention.value?.[1] || '').toLowerCase()),
    )
    .slice(0, 8),
)
const colors = ['#ffffff', '#fa551e', '#f39c20', '#f4d42a', '#7bd65b', '#4798fa', '#8257ef']
function insert(value: string) {
  const start = input.value?.selectionStart ?? body.value.length,
    end = input.value?.selectionEnd ?? start
  if (body.value.length - end + start + value.length > 5000) return
  body.value = body.value.slice(0, start) + value + body.value.slice(end)
  emojiOpen.value = false
  nextTick(() => {
    input.value?.focus()
    input.value?.setSelectionRange(start + value.length, start + value.length)
  })
}
function selectMember(name: string) {
  body.value = body.value.replace(/@[^\s@]*$/, `@${name} `)
  input.value?.focus()
}
</script>
<template>
  <div class="comment-compose-shell">
    <div v-if="drawing && !floating" class="comment-palette">
      <button
        v-for="value in colors"
        :key="value"
        :style="{ background: value }"
        :aria-label="`画笔颜色 ${value}`"
        :aria-pressed="color === value"
        :disabled="disabled"
        @click="emit('color', value)"
      /><span /><button
        class="comment-tool"
        :aria-pressed="tool === 'path'"
        aria-label="自由画笔"
        @click="emit('tool', 'path')"
      >
        <IconPencil :size="17" /></button
      ><button
        class="comment-tool"
        :aria-pressed="tool === 'point'"
        aria-label="定位标记"
        @click="emit('tool', 'point')"
      >
        <IconBrush :size="17" />
      </button>
    </div>
    <div v-if="emojiOpen" class="comment-emoji-pop"><CommentEmojiPicker @select="insert" /></div>
    <div v-if="mention" class="comment-mention-pop">
      <button
        v-for="member in matches"
        :key="member.userId"
        @click="selectMember(member.displayName)"
      >
        @{{ member.displayName }}</button
      ><span v-if="!matches.length">没有匹配的项目成员</span>
    </div>
    <div class="comment-compose-box">
      <textarea
        ref="input"
        v-model="body"
        :disabled="disabled"
        maxlength="5000"
        rows="1"
        placeholder="添加评论…"
        aria-label="评论正文"
        @keydown.ctrl.enter.prevent="!disabled && !blocked && body.trim() && emit('send')"
      />
      <div class="comment-compose-tools">
        <button
          v-if="!floating && annotation"
          aria-label="开启画布标注"
          :aria-pressed="drawing"
          :disabled="disabled"
          @click="emit('drawing')"
        >
          <IconBrush :size="18" /></button
        ><button
          aria-label="选择表情"
          :aria-expanded="emojiOpen"
          :disabled="disabled"
          @click="emojiOpen = !emojiOpen"
        >
          <IconMoodSmile :size="18" /></button
        ><button
          v-if="floating || editing"
          aria-label="提及项目成员"
          :disabled="disabled"
          @click="insert(' @')"
        >
          <IconAt :size="18" /></button
        ><span /><button
          v-if="floating || editing"
          aria-label="取消评论编辑"
          :disabled="disabled"
          @click="emit('cancel')"
        >
          <IconX :size="18" /></button
        ><button
          class="comment-send"
          :aria-label="editing ? '保存修改' : '发送评论'"
          :disabled="disabled || blocked || !body.trim()"
          @click="emit('send')"
        >
          <IconCheck v-if="editing" :size="19" /><IconArrowUp v-else :size="20" />
        </button>
      </div>
    </div>
  </div>
</template>
<style scoped>
.comment-compose-shell {
  position: relative;
  width: 100%;
  font-size: 13px;
}
.comment-compose-box {
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 10px 8px 8px;
  background: var(--surface-hover);
}
textarea {
  display: block;
  width: 100%;
  min-height: 26px;
  max-height: 110px;
  resize: vertical;
  background: none;
  border: 0;
  outline: none;
  color: var(--foreground);
  font: inherit;
}
.comment-compose-tools {
  display: flex;
  align-items: center;
  gap: 3px;
  margin-top: 5px;
}
.comment-compose-tools span {
  flex: 1;
}
button {
  display: grid;
  place-items: center;
  border: 0;
  background: transparent;
  color: var(--foreground);
  cursor: pointer;
  border-radius: 50%;
  padding: 5px;
}
button:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
button:focus-visible {
  outline: 2px solid var(--primary);
}
button[aria-pressed='true'] {
  color: var(--primary);
}
.comment-compose-tools .comment-send {
  width: 28px;
  height: 28px;
  background: var(--primary);
  color: var(--primary-foreground);
}
.comment-emoji-pop,
.comment-mention-pop {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 0;
  right: 0;
  z-index: 5;
  border: 1px solid var(--border);
  border-radius: 16px;
  background: var(--surface-raised);
  box-shadow: 0 8px 20px #0003;
}
.comment-mention-pop {
  display: grid;
  padding: 8px;
}
.comment-mention-pop button {
  border-radius: 6px;
  justify-content: start;
}
.comment-mention-pop span {
  padding: 8px;
  color: var(--muted-foreground);
}
.comment-palette {
  display: flex;
  align-items: center;
  gap: 9px;
  border-radius: 40px;
  background: var(--surface-raised);
  padding: 10px;
  margin-bottom: 8px;
  border: 1px solid var(--border);
}
.comment-palette button {
  width: 20px;
  height: 20px;
  padding: 0;
  flex-shrink: 0;
}
.comment-palette button[aria-pressed='true'] {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}
.comment-palette span {
  flex: 1;
}
.comment-palette .comment-tool {
  width: 23px;
  height: 23px;
}
</style>
