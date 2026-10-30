<script setup lang="ts">
import {
  IconDotsVertical,
  IconCheck,
  IconMessageCircle,
} from '@tabler/icons-vue'
import { computed, ref, watch } from 'vue'
import CommentCanvas from './CommentCanvas.vue'
import CommentComposer from './CommentComposer.vue'
import CommentCard from './CommentCard.vue'
import { useCommentOverview } from '@/composables/useCommentOverview'
import { useCommentCollaboration } from '@/composables/useCommentCollaboration'
import CommentImageAnnotations from './CommentImageAnnotations.vue'
import {
  ElPopover,
  ElForm,
  ElFormItem,
  ElInput,
  ElSelect,
  ElOption,
  ElPagination,
  ElMessageBox,
} from 'element-plus'
import type { CommentTarget, MediaComment } from '@/api/comments'
import { useMediaComments } from '@/composables/useMediaComments'
import Button from '@/components/ui/Button.vue'
import { useAuthStore } from '@/stores/auth'
import { useCommentVideo } from '@/composables/useCommentVideo'
import { validCommentVideoTime } from '@/utils/commentVideoTime'
const props = defineProps<{
  target: CommentTarget
  mediaKind?: string
  visible?: boolean
  sidebar?: boolean
  projectId?: string
  canvasHost?: HTMLElement
  sourceWidth?: number
  sourceHeight?: number
}>()
const viewedAnnotations = ref<string>()
watch([() => JSON.stringify(props.target), () => useAuthStore().token], () => {
  viewedAnnotations.value = undefined
})
const video = useCommentVideo(
  () => props.target,
  () => props.visible !== false,
)
const { player, url: videoUrl } = video
const {
  sendFromSidebar,
  canRead,
  canCreate,
  retryBlocked,
  form,
  confirmLeave,
  runConfirmed,
  threads,
  rows,
  threadId,
  threadPage,
  threadTotal,
  page,
  total,
  body,
  videoTime,
  annotations,
  updateAnnotations,
  parent,
  editing,
  loading,
  threadLoading,
  threadError,
  commentsError,
  saving,
  locked,
  uncertain,
  retry,
  error,
  notice,
  loadThreads,
  refresh,
  resetEditor,
  reply,
  edit,
  mutate,
} = useMediaComments(
  () => props.target,
  () => props.mediaKind || '',
  () => props.visible !== false,
)
watch(threads, (list) => {
  if (props.sidebar && !threadId.value && !body.value && list.length) threadId.value = list[0]!.id
})
const selectedId = ref(''),
  drawing = ref(false),
  color = ref('#fa551e'),
  tool = ref<'path' | 'point'>('path'),
  search = ref(''),
  filter = ref('all')
const overview = useCommentOverview(
  () => props.target,
  () => props.sidebar === true && props.visible !== false,
)
const collaboration = useCommentCollaboration(
  () => props.projectId,
  () => JSON.stringify(props.target),
  overview.reload,
  overview.reload,
)
watch(rows, () => {
  if (props.sidebar) void overview.reload()
})
const currentThread = computed(() =>
  overview.threads.value.find(
    (item) =>
      item.id ===
      (overview.rows.value.find((row) => row.id === selectedId.value)?.threadId || threadId.value),
  ),
)
const resolved = computed(() => !!currentThread.value?.resolvedAt)
const busy = computed(() => locked.value || collaboration.pending.value)
const blocked = computed(() => !!threadError.value || threadLoading.value || !canCreate.value)
const filteredRows = computed(() =>
  overview.rows.value.filter(
    (row) =>
      (!search.value || row.body?.includes(search.value)) &&
      (filter.value === 'all' || (filter.value === 'resolved') === isResolved(row)),
  ),
)
watch(
  () => JSON.stringify(props.target),
  () => {
    selectedId.value = ''
    drawing.value = false
  },
)
function isResolved(row: MediaComment) {
  return !!overview.threads.value.find((thread) => thread.id === row.threadId)?.resolvedAt
}
async function send() {
  await sendFromSidebar(true)
  await overview.reload()
  if (!body.value && !error.value) {
    drawing.value = false
    selectedId.value = overview.rows.value.filter((row) => !row.deleted).at(-1)?.id || ''
  }
}
function cancelDraft() {
  if (busy.value) return
  resetEditor()
  drawing.value = false
  selectedId.value = ''
}
async function resolveThread(row?: MediaComment) {
  if (row) selectedId.value = row.id
  if (currentThread.value)
    await collaboration.update(currentThread.value, resolved.value ? 'reopen' : 'resolve')
}
async function deleteThread() {
  const thread = currentThread.value
  if (!thread) return
  const confirmed = await ElMessageBox.confirm('删除此讨论及其画布标记？', '删除讨论', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'warning',
  }).catch(() => false)
  if (confirmed && currentThread.value?.id === thread.id) {
    await collaboration.update(thread, 'delete')
    if (!collaboration.error.value) {
      threadId.value = ''
      selectedId.value = ''
      await loadThreads()
    }
  }
}
defineExpose({ confirmLeave })
async function selectThread(value: string) {
  if (value === threadId.value) return
  await runConfirmed(() => {
    threadId.value = value
  })
}
async function startDiscussion() {
  await runConfirmed(() => mutate('thread'))
}
async function startReply(row: MediaComment) {
  await runConfirmed(() => {
    threadId.value = row.threadId
    selectedId.value = row.id
    reply(row)
  })
}
async function startEdit(row: MediaComment) {
  await runConfirmed(() => {
    threadId.value = row.threadId
    selectedId.value = row.id
    edit(row)
  })
}
async function cancelEdit() {
  await runConfirmed(resetEditor)
}
const rules = {
  body: [{ required: true, whitespace: true, message: '请输入评论正文' }],
  videoTime: [
    {
      validator: (_rule: unknown, value: string, callback: (error?: Error) => void) =>
        callback(
          !value || validCommentVideoTime(value)
            ? undefined
            : new Error('请输入非负秒数，最多六位小数'),
        ),
    },
  ],
}
async function remove(row: MediaComment) {
  await runConfirmed(async () => {
    const token = useAuthStore().token,
      target = JSON.stringify(props.target),
      thread = threadId.value
    const confirmed = await ElMessageBox.confirm(
      '删除此评论后保留回复，正文和标注不再展示。',
      '删除评论',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    ).catch(() => false)
    if (
      confirmed &&
      token === useAuthStore().token &&
      target === JSON.stringify(props.target) &&
      thread === threadId.value
    ) {
      threadId.value = row.threadId
      await mutate('delete', row)
      await overview.reload()
    }
  })
}
</script>
<template>
  <section
    class="media-comments"
    :class="{ 'media-comments-sidebar': sidebar }"
    aria-label="媒体版本评论"
  >
    <template v-if="sidebar">
      <div v-if="overview.rows.value.length" class="sidebar-comment-topbar">
        <ElInput v-model="search" placeholder="搜索评论" aria-label="搜索评论" /><ElSelect
          v-model="filter"
          aria-label="筛选评论"
          ><ElOption label="全部" value="all" /><ElOption label="未解决" value="open" /><ElOption
            label="已解决"
            value="resolved"
        /></ElSelect>
      </div>
      <div class="sidebar-comment-list">
        <p v-if="overview.loading.value" role="status">正在加载评论…</p>
        <div
          v-else-if="overview.error.value || commentsError || !canRead"
          class="sidebar-comment-empty"
        >
          <span class="sidebar-comment-empty-icon"><IconMessageCircle :size="24" /></span>
          <p role="alert">{{ overview.error.value || commentsError || '当前没有评论阅读权限' }}</p>
          <Button @click="threadId ? refresh() : loadThreads()">重新加载</Button>
        </div>
        <div v-else-if="!overview.rows.value.length" class="sidebar-comment-empty">
          <span class="sidebar-comment-empty-icon"><IconMessageCircle :size="24" /></span
          ><strong>暂无评论</strong>
        </div>
        <CommentCard
          v-for="row in filteredRows"
          :key="row.id"
          :row="row"
          :selected="selectedId === row.id"
          :resolved="isResolved(row)"
          :disabled="busy"
          :can-create="canCreate"
          :editing="editing?.id === row.id"
          @select="selectedId = row.id"
          @reply="startReply(row)"
          @edit="startEdit(row)"
          @remove="remove(row)"
          @react="(emoji) => collaboration.react(row, emoji)"
          @resolve="resolveThread(row)"
          ><template #editor
            ><CommentComposer
              v-model="body"
              editing
              :disabled="busy"
              :members="collaboration.members.value"
              @send="send"
              @cancel="cancelDraft" /></template
        ></CommentCard>
      </div>
      <p v-if="error || collaboration.error.value" role="alert">
        {{ error || collaboration.error.value }}
      </p>
      <Button v-if="uncertain" :disabled="saving || retryBlocked" @click="retry"
        >重试确认结果</Button
      >
      <ElForm ref="form" :model="{ body, videoTime }" :rules="rules" class="comment-sidebar-form">
        <ElFormItem prop="body"
          ><CommentComposer
            v-show="!editing && !annotations.length"
            v-model="body"
            :disabled="busy || !canCreate"
            :blocked="blocked"
            :members="collaboration.members.value"
            :annotation="mediaKind === 'image'"
            :drawing="drawing"
            :color="color"
            :tool="tool"
            @drawing="drawing = !drawing"
            @color="color = $event"
            @tool="tool = $event"
            @send="send"
        /></ElFormItem>
        <p v-if="parent" class="sidebar-comment-reply">
          回复 #{{ parent.id }} <button @click="cancelDraft">取消</button>
        </p>
        <ElFormItem v-if="mediaKind === 'video'" prop="videoTime"
          ><ElInput v-model="videoTime" placeholder="视频时间点（秒，可选）" :disabled="busy"
        /></ElFormItem>
      </ElForm>
      <CommentCanvas
        v-if="canvasHost && sourceWidth && sourceHeight && mediaKind === 'image'"
        :host="canvasHost"
        :width="sourceWidth"
        :height="sourceHeight"
        :drawing="drawing"
        :disabled="busy || blocked"
        :color="color"
        :tool="tool"
        :comments="overview.rows.value"
        :resolved-ids="overview.rows.value.filter(isResolved).map((row) => row.id)"
        :selected-id="selectedId"
        :resolved="resolved"
        :model-value="annotations"
        @update:model-value="updateAnnotations"
        @select="selectedId = $event"
        @draft="drawing = false"
      >
        <template #draft
          ><CommentComposer
            v-model="body"
            floating
            :editing="!!editing"
            :disabled="busy"
            :blocked="blocked"
            :members="collaboration.members.value"
            @send="send"
            @cancel="cancelDraft"
        /></template>
        <template #thread-tools>
          <ElPopover trigger="click" placement="bottom-end" :width="160"><template #reference><button aria-label="讨论更多操作" :disabled="busy"><IconDotsVertical :size="17" /></button></template><Button variant="ghost" :disabled="busy" @click="deleteThread">删除讨论</Button></ElPopover>
          <button :disabled="busy" :class="{ 'thread-resolved': resolved }" :title="resolved?'重新打开':'标记为已解决'" aria-label="切换讨论解决状态" @click="resolveThread()"><IconCheck :size="17" /></button>
        </template>
        <template #comment="{ comment }"
          ><CommentCard
            :row="comment"
            :resolved="resolved"
            :disabled="busy"
            :can-create="canCreate"
            :editing="editing?.id === comment.id"
            @edit="startEdit(comment)"
            @remove="remove(comment)"
            @reply="startReply(comment)"
            @react="(emoji) => collaboration.react(comment, emoji)"
            @resolve="resolveThread"
            ><template #editor
              ><CommentComposer
                v-model="body"
                editing
                :disabled="busy"
                :members="collaboration.members.value"
                @send="send"
                @cancel="cancelDraft" /></template></CommentCard
        ></template>
      </CommentCanvas>
    </template>
    <template v-else>
      <div class="comment-toolbar">
        <h3>版本评论</h3>
        <Button variant="ghost" :disabled="!canRead || locked || threadLoading" @click="loadThreads"
          >刷新主题</Button
        >
        <Button v-if="canCreate" variant="ghost" :disabled="locked" @click="startDiscussion"
          >新建讨论</Button
        >
      </div>
      <p v-if="!canRead" class="muted">当前没有评论阅读权限。</p>
      <p v-if="threadLoading" role="status">正在加载讨论主题…</p>
      <p v-else-if="threadError" class="project-error" role="alert">{{ threadError }}</p>
      <p v-else-if="!threads.length" class="muted">当前页暂无讨论主题。</p>
      <ElSelect
        :model-value="threadId"
        placeholder="选择讨论主题"
        :disabled="locked || threadLoading || !!threadError"
        aria-label="讨论主题"
        @update:model-value="selectThread"
      >
        <ElOption
          v-for="thread in threads"
          :key="thread.id"
          :value="thread.id"
          :label="`讨论 ${thread.id} · ${thread.createTime}`"
        />
      </ElSelect>
      <ElPagination
        v-if="threadTotal > 10"
        v-model:current-page="threadPage"
        :page-size="10"
        :total="threadTotal"
        :disabled="locked"
        layout="prev, pager, next"
      />
      <p v-if="error" class="project-error" role="alert">{{ error }}</p>
      <p v-if="uncertain" role="alert">上次操作结果未确认，请重试原请求。</p>
      <p v-if="retryBlocked" class="muted">
        当前权限不允许重试。可先关闭此面板；本次登录内恢复权限并重新打开后，可继续核对原请求。
      </p>
      <Button v-if="uncertain" :disabled="saving || retryBlocked" @click="retry"
        >重试确认结果</Button
      >
      <p v-if="notice" role="status">{{ notice }}</p>
      <section v-if="mediaKind === 'video'" aria-label="评论视频定位">
        <Button variant="ghost" :disabled="video.loading.value" @click="video.open()">{{
          video.loading.value ? '正在读取视频…' : '打开定位播放器'
        }}</Button>
        <p v-if="video.error.value" role="alert" class="project-error">{{ video.error.value }}</p>
        <video
          v-if="videoUrl"
          ref="player"
          :src="videoUrl"
          controls
          preload="metadata"
          class="comment-video"
          @loadedmetadata="video.seekReady"
        />
      </section>
      <template v-if="threadId">
        <Button variant="ghost" :disabled="locked || loading" @click="refresh">刷新评论</Button>
        <p v-if="loading" role="status">正在加载评论…</p>
        <p v-else-if="commentsError" class="project-error" role="alert">{{ commentsError }}</p>
        <article v-for="row in rows" :key="row.id" class="media-comment">
          <small class="muted"
            >#{{ row.id }} · {{ row.author?.displayName || '已删除评论'
            }}<span v-if="row.parentId"> · 回复 #{{ row.parentId }}</span></small
          >
          <p class="comment-body">{{ row.deleted ? '此评论已删除' : row.body }}</p>
          <Button
            v-if="row.videoTime != null && mediaKind === 'video'"
            variant="ghost"
            @click="video.open(row.videoTime)"
            >定位到 {{ row.videoTime }} 秒</Button
          >
          <Button
            v-if="row.annotations.length && mediaKind === 'image'"
            variant="ghost"
            @click="viewedAnnotations = viewedAnnotations === row.id ? undefined : row.id"
            >{{
              viewedAnnotations === row.id
                ? '收起标注'
                : `查看 ${row.annotations.length} 个图片标注`
            }}</Button
          >
          <CommentImageAnnotations
            v-if="viewedAnnotations === row.id && !row.deleted"
            :visible="visible !== false"
            :target="target"
            :model-value="row.annotations"
            readonly
          />
          <div v-if="!row.deleted">
            <Button v-if="canCreate" variant="ghost" :disabled="locked" @click="startReply(row)"
              >回复</Button
            >
            <Button
              v-if="row.allowedActions?.includes('edit')"
              variant="ghost"
              :disabled="locked"
              @click="startEdit(row)"
              >编辑</Button
            >
            <Button
              v-if="row.allowedActions?.includes('delete')"
              variant="ghost"
              :disabled="locked"
              @click="remove(row)"
              >删除</Button
            >
          </div>
        </article>
        <p v-if="!loading && !commentsError && !rows.length" class="muted">暂无评论。</p>
        <ElPagination
          v-if="total > 30"
          v-model:current-page="page"
          :page-size="30"
          :total="total"
          :disabled="locked"
          layout="prev, pager, next"
        />
        <ElForm
          v-if="canCreate || editing"
          ref="form"
          :model="{ body, videoTime }"
          :rules="rules"
          :disabled="locked"
          label-position="top"
        >
          <p v-if="editing">编辑评论 #{{ editing.id }}；未操作画板时保留原标注。</p>
          <p v-if="editing?.videoTime != null" class="muted">
            原视频时间点 {{ editing.videoTime }} 秒保持不变。
          </p>
          <p v-else-if="parent">回复 #{{ parent.id }}</p>
          <ElFormItem label="评论正文" prop="body"
            ><ElInput v-model="body" type="textarea" :rows="3" maxlength="5000" show-word-limit
          /></ElFormItem>
          <ElFormItem v-if="mediaKind === 'image'" label="图片定位标注（可选）">
            <CommentImageAnnotations
              :visible="visible !== false"
              :target="target"
              :model-value="annotations"
              :disabled="locked"
              @update:model-value="updateAnnotations"
            />
          </ElFormItem>
          <ElFormItem
            v-if="mediaKind === 'video' && !editing"
            label="视频时间点（秒，可选）"
            prop="videoTime"
          >
            <ElInput
              v-model="videoTime"
              inputmode="decimal"
              placeholder="例如 12.345678"
              maxlength="19"
            />
            <Button
              variant="ghost"
              :disabled="locked || !videoUrl"
              @click="videoTime = video.currentTime()"
              >使用播放器当前时间</Button
            >
          </ElFormItem>
          <Button :disabled="locked" @click="mutate('save')">{{
            saving ? '保存中…' : editing ? '保存修改' : '发表评论'
          }}</Button>
          <Button v-if="editing || parent" variant="ghost" :disabled="locked" @click="cancelEdit"
            >取消编辑/回复</Button
          >
        </ElForm>
      </template>
      <p v-else class="muted">选择已有主题或新建讨论。评论仅属于当前固定素材版本或作品。</p>
    </template>
  </section>
</template>
<style scoped>
.media-comments {
  margin-top: 20px;
  border-top: 1px solid var(--border);
  padding-top: 12px;
}
.comment-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.comment-toolbar h3 {
  margin-right: auto;
}
.media-comment {
  padding: 12px 0;
  border-bottom: 1px solid var(--border);
}
.comment-body {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.comment-video {
  display: block;
  width: 100%;
  max-height: 45vh;
  margin: 12px 0;
}
</style>

<style scoped>
.media-comments-sidebar {
  margin: 0;
  padding: 0;
  border: 0;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.sidebar-comment-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
}
.sidebar-comment-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 22px;
  text-align: center;
  font-size: 14px;
  padding: 24px 12px;
}
.sidebar-comment-empty p {
  color: var(--muted-foreground);
  font-size: 12px;
  margin: 0;
}
.sidebar-comment-empty-icon {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  border: 1px solid var(--border);
  background: radial-gradient(circle at 50% 20%, var(--surface-hover), var(--surface));
  box-shadow:
    inset 0 0 8px #ffffff25,
    0 3px 8px #0002;
}
.sidebar-comment-topbar {
  display: flex;
  gap: 6px;
}
.sidebar-comment {
  display: flex;
  gap: 10px;
  padding: 14px 8px;
  font-size: 13px;
}
.sidebar-comment > div {
  min-width: 0;
  flex: 1;
}
.sidebar-comment small {
  display: block;
  color: var(--muted-foreground);
}
.sidebar-comment-avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--surface-hover);
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.sidebar-comment-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.sidebar-comment-controls button,
.sidebar-comment-reply button {
  background: none;
  border: 0;
  color: var(--muted-foreground);
  cursor: pointer;
  font-size: 12px;
}
.sidebar-comment-composer {
  flex-shrink: 0;
  padding: 8px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: var(--surface-hover);
}
.sidebar-comment-composer .el-form-item {
  margin: 0;
}
.sidebar-comment-composer :deep(.el-textarea__inner) {
  padding: 0;
  resize: none;
  background: transparent;
  box-shadow: none;
  color: var(--foreground);
  font-size: 14px;
}
.sidebar-comment-composer :deep(.el-form-item__error) {
  position: static;
}
.sidebar-comment-compose-tools {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 8px;
}
.sidebar-comment-compose-tools button {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: 50%;
  color: var(--foreground);
  background: none;
  cursor: pointer;
}
.sidebar-comment-compose-tools .sidebar-comment-send {
  margin-left: auto;
  background: var(--primary);
  color: var(--primary-foreground);
}
.sidebar-comment-compose-tools button:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
.sidebar-comment-compose-tools button:focus-visible {
  outline: 2px solid var(--focus);
  outline-offset: 2px;
}
.sidebar-comment-reply {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  margin-bottom: 8px;
}
.sidebar-comment-annotations {
  max-height: 260px;
  overflow: auto;
}
</style>

<style scoped>
.comment-sidebar-form {
  flex-shrink: 0;
}
.comment-sidebar-form .el-form-item {
  margin-bottom: 0;
}
.sidebar-comment-topbar .el-select {
  width: 105px;
  flex-shrink: 0;
}
</style>

<style scoped>
.thread-resolved {background:var(--primary)!important;color:var(--primary-foreground)!important}
</style>
