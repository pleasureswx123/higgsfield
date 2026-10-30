<script setup lang="ts">
import { computed } from 'vue'
import { ElPopover } from 'element-plus'
import {
  IconDotsVertical,
  IconCheck,
  IconMoodSmile,
  IconBrush,
  IconPencil,
  IconTrash,
} from '@tabler/icons-vue'
import type { MediaComment } from '@/api/comments'
import CommentEmojiPicker from './CommentEmojiPicker.vue'
const props = defineProps<{
  row: MediaComment
  selected?: boolean
  resolved?: boolean
  disabled?: boolean
  canCreate?: boolean
  editing?: boolean
}>()
const emit = defineEmits<{
  select: []
  reply: []
  edit: []
  remove: []
  react: [emoji: string]
  resolve: []
}>()
const reactions = computed(() => {
  const result = new Map<string, number>()
  for (const item of props.row.reactions || [])
    result.set(item.emoji, (result.get(item.emoji) || 0) + 1)
  return [...result]
})
const time = computed(() =>
  new Date(props.row.createTime).toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }),
)
</script>
<template>
  <article class="comment-card" :class="{ selected, resolved }" @click="emit('select')">
    <div class="comment-card-avatar">{{ row.author?.displayName.slice(0, 1) || '评' }}</div>
    <div class="comment-card-main">
      <header>
        <strong>{{ row.author?.displayName || '已删除评论' }}</strong
        ><time>{{ time }}</time>
        <div class="comment-card-actions" @click.stop>
          <button
            v-if="row.allowedActions?.includes('edit')"
            :title="resolved ? '重新打开讨论' : '标记为已解决'"
            :aria-label="resolved ? '重新打开讨论' : '标记为已解决'"
            :class="{ done: resolved }"
            :disabled="disabled"
            @click="emit('resolve')"
          >
            <IconCheck :size="14" /></button
          ><ElPopover trigger="click" placement="bottom-end" :width="150"
            ><template #reference
              ><button aria-label="评论更多操作" :disabled="disabled">
                <IconDotsVertical :size="16" /></button
            ></template>
            <div class="comment-card-menu">
              <button v-if="row.allowedActions?.includes('edit')" @click="emit('edit')">
                <IconPencil :size="16" />编辑</button
              ><button v-if="row.allowedActions?.includes('delete')" @click="emit('remove')">
                <IconTrash :size="16" />删除
              </button>
            </div></ElPopover
          >
        </div>
      </header>
      <slot v-if="editing" name="editor" /><template v-else
        ><p class="comment-card-body">
          <IconBrush v-if="row.annotations.length" :size="16" />{{
            row.deleted ? '此评论已删除' : row.body
          }}
        </p>
        <div v-if="!row.deleted" class="comment-card-reactions" @click.stop>
          <button
            v-for="[emoji, count] in reactions"
            :key="emoji"
            :disabled="disabled || !canCreate"
            @click="emit('react', emoji)"
          >
            {{ emoji }} {{ count }}</button
          ><ElPopover v-if="canCreate" trigger="click" placement="top" :width="320"
            ><template #reference
              ><button aria-label="回应表情" :disabled="disabled">
                <IconMoodSmile :size="16" /></button></template
            ><CommentEmojiPicker @select="(emoji) => emit('react', emoji)"
          /></ElPopover>
        </div>
        <footer>
          <button v-if="canCreate && !row.deleted" :disabled="disabled" @click.stop="emit('reply')">
            回复</button
          ><span>#{{ row.id }}</span>
        </footer></template
      >
    </div>
  </article>
</template>
<style scoped>
.comment-card {
  display: flex;
  gap: 8px;
  padding: 10px;
  background: var(--surface-hover);
  border: 1px solid transparent;
  border-radius: 13px;
  font-size: 13px;
  cursor: pointer;
  margin-bottom: 10px;
}
.comment-card.selected {
  border-color: var(--muted-foreground);
  background: var(--surface-raised);
}
.comment-card.resolved .comment-card-body,
.comment-card.resolved header strong {
  opacity: 0.5;
}
.comment-card-avatar {
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--surface-raised);
}
.comment-card-main {
  min-width: 0;
  flex: 1;
}
header {
  display: flex;
  gap: 6px;
  align-items: center;
}
header strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 110px;
}
time {
  color: var(--muted-foreground);
  font-size: 10px;
}
.comment-card-actions {
  display: flex;
  margin-left: auto;
  opacity: 0;
}
.comment-card:hover .comment-card-actions,
.comment-card:focus-within .comment-card-actions {
  opacity: 1;
}
button {
  background: none;
  border: 0;
  color: var(--muted-foreground);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px;
  border-radius: 6px;
}
button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.comment-card-actions .done {
  background: var(--primary);
  color: var(--primary-foreground);
  border-radius: 50%;
}
.comment-card-body {
  margin: 8px 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.comment-card-body svg {
  vertical-align: middle;
  color: #6095ff;
  margin-right: 5px;
}
.comment-card-reactions {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
}
.comment-card-reactions button:not(:last-child) {
  border: 1px solid #6095ff;
  background: #6095ff20;
}
footer {
  display: flex;
  justify-content: space-between;
  color: var(--muted-foreground);
  font-size: 12px;
  margin-top: 6px;
}
.comment-card-menu {
  display: grid;
  gap: 6px;
}
.comment-card-menu button {
  padding: 8px;
}
</style>
