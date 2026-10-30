<script setup lang="ts">
import { formatVideoTime } from '@/utils/videoTime'
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
  timecode?: boolean
  compact?: boolean
  statusColor?: string | null
  row: MediaComment
  selected?: boolean
  resolved?: boolean
  disabled?: boolean
  canCreate?: boolean
  editing?: boolean
}>()
const emit = defineEmits<{
  color: [value: string | null]
  select: []
  reply: []
  edit: []
  remove: []
  react: [emoji: string]
  resolve: []
}>()
const statusColors = [null, '#ffffff', '#fa551e', '#f39c20', '#f4d42a', '#7bd65b', '#4798fa', '#8257ef']
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
          <ElPopover v-if="!compact && !row.parentId && row.allowedActions?.includes('edit')" trigger="click" placement="bottom-end" :width="260">
            <template #reference><button type="button" class="comment-status-color" title="状态颜色" aria-label="状态颜色" :disabled="disabled"><span class="status-dot" :style="{background: statusColor || 'transparent'}" /></button></template>
            <div class="status-palette"><button v-for="value in statusColors" :key="value || 'none'" type="button" :aria-label="value ? `状态颜色 ${value}` : '清除状态颜色'" :aria-pressed="(statusColor || null) === value" :style="{background:value || 'transparent'}" @click="emit('color',value)" /></div>
          </ElPopover>
          <ElPopover v-if="canCreate" trigger="click" placement="top" :width="320"><template #reference><button type="button" title="回应表情" aria-label="回应表情" :disabled="disabled"><IconMoodSmile :size="16" /></button></template><CommentEmojiPicker @select="emoji => emit('react', emoji)" /></ElPopover>
          <button type="button"
            v-if="!compact && !row.parentId && row.allowedActions?.includes('edit')"
            :title="resolved ? '重新打开讨论' : '标记为已解决'"
            :aria-label="resolved ? '重新打开讨论' : '标记为已解决'"
            :class="{ done: resolved }"
            :disabled="disabled"
            @click="emit('resolve')"
          >
            <IconCheck :size="14" /></button
          ><ElPopover trigger="click" placement="bottom-end" :width="150"
            ><template #reference
              ><button type="button" aria-label="评论更多操作" :disabled="disabled">
                <IconDotsVertical :size="16" /></button
            ></template>
            <div class="comment-card-menu">
              <button type="button" v-if="row.allowedActions?.includes('edit')" @click="emit('edit')">
                <IconPencil :size="16" />编辑</button
              ><button type="button" v-if="row.allowedActions?.includes('delete')" @click="emit('remove')">
                <IconTrash :size="16" />删除
              </button>
            </div></ElPopover
          >
        </div>
      </header>
      <slot v-if="editing" name="editor" /><template v-else
        ><p class="comment-card-body">
          <button v-if="!row.parentId && row.videoTime != null" type="button" class="comment-time-badge" :aria-label="`定位到 ${formatVideoTime(row.videoTime, timecode)}`" @click.stop="emit('select')">{{ formatVideoTime(row.videoTime, timecode) }}</button>
          <IconBrush v-if="row.annotations.length" :size="16" />{{
            row.deleted ? '此评论已删除' : row.body
          }}
        </p>
        <div v-if="!row.deleted && reactions.length" class="comment-card-reactions" @click.stop>
          <button type="button"
            v-for="[emoji, count] in reactions"
            :key="emoji"
            :disabled="disabled || !canCreate"
            @click="emit('react', emoji)"
          >
            {{ emoji }} {{ count }}</button
          >
        </div>
        <footer v-if="!compact">
          <button type="button" v-if="canCreate && !row.deleted" :disabled="disabled" @click.stop="emit('reply')">
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
}
/* 状态色常驻，其余操作仅在悬停或键盘聚焦时显示。 */
.comment-card-actions > :not(.comment-status-color) {
  display: none;
}
.comment-card:hover .comment-card-actions > :not(.comment-status-color),
.comment-card:focus-within .comment-card-actions > :not(.comment-status-color) {
  display: inline-flex;
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
.comment-card-reactions button {
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

<style scoped>
.status-dot { width: 13px; height: 13px; border: 1px dotted var(--muted-foreground); border-radius: 50%; }
.status-palette { display: flex; justify-content: space-between; gap: 8px; }
.status-palette button { width: 20px; height: 20px; border-radius: 50%; border: 1px dotted var(--muted-foreground); padding: 0; }
.status-palette button[aria-pressed='true'] { outline: 1px solid var(--primary); outline-offset: 2px; }
.comment-card-menu button:last-child { color: var(--el-color-danger); }
</style>

<style scoped>
.comment-time-badge { display:inline-flex; padding:1px 5px; margin-right:5px; background:var(--surface); color:var(--foreground); border-radius:4px; font-size:11px; font-weight:600; }
</style>
