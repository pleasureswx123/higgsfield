<script setup lang="ts">
import { ElSelect, ElOption, ElPagination, ElDialog } from 'element-plus'
import Button from '@/components/ui/Button.vue'
import { useFavorites } from '@/composables/useFavorites'
import { useFavoritePreview } from '@/composables/useFavoritePreview'
import '@/styles/elements.css'
const { rows, total, page, kind, loading, error, pending, refresh, remove } = useFavorites()
const preview = useFavoritePreview()
const { assetOpen, title, url, mediaType } = preview
const kinds = { element: '元素', asset: '素材', output: '作品' }
</script>
<template>
  <section class="projects-page element-workspace">
    <div class="project-page-heading">
      <div>
        <h1>我的收藏</h1>
        <p class="muted">集中查看收藏的元素、素材和作品。</p>
      </div>
      <Button variant="ghost" :disabled="loading || !!pending" @click="refresh">刷新</Button>
    </div>
    <div class="element-toolbar">
      <ElSelect v-model="kind" aria-label="收藏类型"
        ><ElOption label="全部类型" value="" /><ElOption
          v-for="(label, value) in kinds"
          :key="value"
          :label="label"
          :value="value"
      /></ElSelect>
      <span class="muted">共 {{ total }} 项收藏</span>
    </div>
    <p v-if="error" class="project-error" role="alert">{{ error }}</p>
    <p v-if="loading" role="status">正在加载收藏…</p>
    <div v-else class="element-grid">
      <article v-for="row in rows" :key="row.id" class="favorite-card">
        <small class="muted">{{ kinds[row.kind] }}</small>
        <h2>{{ row.available && row.source ? row.source.name : '内容已不可用' }}</h2>
        <p v-if="!row.available" class="muted">内容可能已删除，或你已失去访问权限。</p>
        <div>
          <Button v-if="row.available && row.source" variant="ghost" @click="preview.open(row)"
            >查看</Button
          >
          <Button variant="ghost" :disabled="!!pending" @click="remove(row.id)">{{
            pending === row.id ? '取消中…' : '取消收藏'
          }}</Button>
        </div>
      </article>
      <p v-if="!rows.length && !error" class="muted">
        暂无收藏，可在元素详情、素材卡片或生成作品中添加。
      </p>
    </div>
    <ElPagination
      v-if="total > 30"
      v-model:current-page="page"
      :page-size="30"
      :total="total"
      layout="prev, pager, next"
    />
    <ElDialog
      v-model="assetOpen"
      :title="title || '内容预览'"
      width="min(960px, 92vw)"
      append-to-body
      @close="preview.clear"
    >
      <p v-if="preview.loading.value" role="status">正在加载媒体…</p>
      <p v-if="preview.error.value" class="project-error" role="alert">{{ preview.error.value }}</p>
      <p v-if="preview.notice.value" class="muted" role="status">{{ preview.notice.value }}</p>
      <pre v-if="mediaType === 'text'" class="favorite-text">{{ preview.text.value }}</pre>
      <img v-if="url && mediaType === 'image'" :src="url" :alt="title" class="favorite-media" />
      <video v-else-if="url" :src="url" controls class="favorite-media" />
    </ElDialog>
  </section>
</template>
<style scoped>
.favorite-card {
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: 12px;
  padding: 18px;
}
.favorite-card h2 {
  font-size: 16px;
  overflow-wrap: anywhere;
}
.favorite-media {
  display: block;
  max-width: 100%;
  max-height: 70vh;
  margin: auto;
}
.favorite-text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font: inherit;
}
</style>
