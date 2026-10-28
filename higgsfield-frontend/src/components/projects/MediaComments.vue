<script setup lang="ts">
import { ref, watch } from 'vue'
import CommentImageAnnotations from './CommentImageAnnotations.vue'
import {
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
const props = defineProps<{ target: CommentTarget; mediaKind?: string; visible?: boolean }>()
const viewedAnnotations = ref<string>()
watch([() => JSON.stringify(props.target), () => useAuthStore().token], () => {
  viewedAnnotations.value = undefined
})
const video = useCommentVideo(() => props.target, () => props.visible !== false)
const { player, url: videoUrl } = video
const {
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
defineExpose({ confirmLeave })
async function selectThread(value: string) {
  if (value === threadId.value) return
  await runConfirmed(() => { threadId.value = value })
}
async function startDiscussion() {
  await runConfirmed(() => mutate('thread'))
}
async function startReply(row: MediaComment) {
  await runConfirmed(() => reply(row))
}
async function startEdit(row: MediaComment) {
  await runConfirmed(() => edit(row))
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
  )
    await mutate('delete', row)
  })
}
</script>
<template>
  <section class="media-comments" aria-label="媒体版本评论">
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
      @update:model-value="selectThread"
      placeholder="选择讨论主题"
      :disabled="locked || threadLoading || !!threadError"
      aria-label="讨论主题"
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
    <Button v-if="uncertain" :disabled="saving || retryBlocked" @click="retry">重试确认结果</Button>
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
            viewedAnnotations === row.id ? '收起标注' : `查看 ${row.annotations.length} 个图片标注`
          }}</Button
        >
        <CommentImageAnnotations
          :visible="visible !== false"
          v-if="viewedAnnotations === row.id && !row.deleted"
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
