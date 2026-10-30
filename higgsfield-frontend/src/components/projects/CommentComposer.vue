<script setup lang="ts">
import { computed, ref, nextTick, onMounted } from 'vue'
import {
  IconMoodSmile,
  IconClock,
  IconAt,
  IconArrowUp,
  IconX,
  IconBrush,
  IconPencil,
  IconCheck,
} from '@tabler/icons-vue'
import { formatVideoTime } from '@/utils/videoTime'
import CommentEmojiPicker from './CommentEmojiPicker.vue'
const props = defineProps<{
  timecode?: boolean
  video?: boolean
  timestamp?: boolean
  time?: number
  inputDisabled?: boolean
  markColor?: string
  disabled?: boolean
  blocked?: boolean
  floating?: boolean
  editing?: boolean
  reply?: boolean
  autofocus?: boolean
  drawing?: boolean
  members?: { userId: string; displayName: string }[]
  color?: string
  tool?: 'path' | 'point'
  annotation?: boolean
}>()
const body = defineModel<string>({ required: true })
const emit = defineEmits<{
  timestamp: []
  send: []
  cancel: []
  drawing: []
  color: [value: string]
  tool: [value: 'path' | 'point']
}>()
const emojiOpen = ref(false),
  input = ref<HTMLTextAreaElement>()
onMounted(() => { if (props.autofocus) void nextTick(() => input.value?.focus()) })
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
  <div class="comment-compose-shell" :class="{ 'video-compose': video && !floating }">
    <div v-if="drawing && !floating" class="comment-palette">
      <button type="button"
        v-for="value in colors"
        :key="value"
        :style="{ background: value }"
        :aria-label="`画笔颜色 ${value}`"
        :aria-pressed="color === value"
        :disabled="disabled"
        @click="emit('color', value)"
      /><span /><button type="button"
        class="comment-tool"
        :aria-pressed="tool === 'path'"
        aria-label="自由画笔"
        @click="emit('tool', 'path')"
      >
        <IconPencil :size="17" /></button
      >
    </div>
    <div v-if="emojiOpen" class="comment-emoji-pop"><CommentEmojiPicker @select="insert" /></div>
    <div v-if="mention" class="comment-mention-pop">
      <button type="button"
        v-for="member in matches"
        :key="member.userId"
        @click="selectMember(member.displayName)"
      >
        @{{ member.displayName }}</button
      ><span v-if="!matches.length">没有匹配的项目成员</span>
    </div>
    <div class="comment-compose-box" :class="{ 'has-mark': markColor, 'has-time': video && timestamp }">
      <div class="compose-input-row">
      <span v-if="video && timestamp" class="compose-time-group">
        <span class="compose-time">{{ formatVideoTime(time || 0, timecode) }}</span>
        <span v-if="!floating" class="compose-time-icon" aria-hidden="true"><IconClock :size="18" /><span class="compose-time-plus">+</span></span>
      </span>
      <IconBrush v-if="markColor" class="compose-mark" :size="15" :style="{ color: markColor }" />
      <textarea
        ref="input"
        v-model="body"
        :disabled="disabled || inputDisabled"
        maxlength="5000"
        rows="1"
        :placeholder="reply ? '回复…' : '添加评论…'"
        aria-label="评论正文"
        @keydown.ctrl.enter.prevent="!disabled && !blocked && body.trim() && emit('send')"
      />
      </div>
      <div class="comment-compose-tools">
        <button v-if="video && !floating" type="button" aria-label="附带视频时间" :aria-pressed="timestamp" :disabled="disabled" @click="emit('timestamp')"><IconClock :size="18" /></button>
        <button type="button"
          v-if="!floating && annotation"
          aria-label="开启画布标注"
          :aria-pressed="drawing"
          :disabled="disabled"
          @click="emit('drawing')"
        >
          <IconBrush :size="18" /></button
        ><button type="button"
          aria-label="选择表情"
          :aria-expanded="emojiOpen"
          :disabled="disabled || inputDisabled"
          @click="emojiOpen = !emojiOpen"
        >
          <IconMoodSmile :size="18" /></button
        ><button type="button"
          v-if="floating || editing"
          aria-label="提及项目成员"
          :disabled="disabled"
          @click="insert(' @')"
        >
          <IconAt :size="18" /></button
        ><span /><button type="button"
          v-if="floating || editing"
          aria-label="取消评论编辑"
          :disabled="disabled"
          @click="emit('cancel')"
        >
          <IconX :size="18" /></button
        ><button type="button"
          class="comment-send"
          :aria-label="editing ? '保存修改' : '发送评论'"
          :disabled="disabled || inputDisabled || blocked || !body.trim()"
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
.compose-mark { flex-shrink: 0; margin-top: 4px; }
.compose-input-row { display: flex; align-items: flex-start; gap: 6px; min-width: 0; }
.compose-input-row textarea { flex: 1; min-width: 0; box-sizing: border-box; padding: 0; }
.comment-compose-box {
  position: relative;
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
  gap: 7px;
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

<style scoped>
.compose-time-group { display:flex; flex-shrink:0; align-items:center; gap:5px; padding-top:1px; }
.compose-time { display:inline-flex; align-items:center; justify-content:center; min-width:44px; height:24px; box-sizing:border-box; padding:0 6px; border-radius:5px; background:color-mix(in srgb,var(--primary) 15%,transparent); color:var(--focus); font-size:12px; line-height:24px; font-weight:700; font-variant-numeric:tabular-nums; }
.compose-time-icon { position:relative; display:grid; place-items:center; width:24px; height:24px; border-radius:5px; background:color-mix(in srgb,var(--primary) 15%,transparent); color:var(--focus); }
.compose-time-plus { position:absolute; right:1px; top:-3px; font-size:13px; font-weight:600; line-height:15px; }
.video-compose { --comment-card-surface:var(--video-compose-surface); }
.video-compose .comment-compose-box { box-sizing:border-box; min-height:88px; border-radius:18px; padding:10px; background:var(--video-compose-surface); }
.video-compose .compose-input-row { gap:9px; }
.video-compose .compose-input-row textarea { font-size:16px; line-height:26px; min-height:26px; resize:none; }
.video-compose .comment-compose-tools { gap:8px; margin-top:7px; }
.video-compose .comment-compose-tools button:not(.comment-send) { width:28px; height:28px; padding:3px; }
.video-compose .comment-compose-tools button svg { width:21px; height:21px; }
.video-compose .comment-compose-tools .comment-send { width:34px; height:34px; }
.video-compose .comment-compose-tools .comment-send svg { width:23px; height:23px; }
</style>
