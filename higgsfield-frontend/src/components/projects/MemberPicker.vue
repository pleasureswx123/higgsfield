<script setup lang="ts">
import { onMounted } from 'vue'
import type { Candidate } from '@/api/projectWorkspace'
import { ElSelect, ElOption } from 'element-plus'
import { useMemberCandidates } from '@/composables/useMemberCandidates'
const props = defineProps<{ projectId: string; disabled?: boolean }>()
const model = defineModel<Candidate>()
const { keyword, items, loading, error, hasNext, load, reset } = useMemberCandidates(props.projectId)
onMounted(reset)
function select(id: string) {
  const item = items.value.find(item => item.userId === id)
  if (item && !item.alreadyMember && !props.disabled) model.value = item
}
</script>
<template>
  <ElSelect :model-value="model?.userId" :disabled="disabled" filterable remote remote-show-suffix
    :remote-method="(value: string) => keyword = value" :loading="loading"
    placeholder="选择人员，可搜索姓名或账号" aria-label="选择项目成员"
    :no-data-text="error || (keyword.trim() ? '没有匹配的人员' : '暂无有效的制作平台使用者')"
    style="width:100%" @change="select">
    <ElOption v-for="item in items" :key="item.userId" :value="item.userId"
      :label="`${item.displayName}（${item.userName}）`" :disabled="item.alreadyMember">
      <span>{{ item.displayName }} <span class="person-account">（{{ item.userName }}）</span></span>
      <span v-if="item.alreadyMember" class="person-status">已加入</span>
    </ElOption>
    <template #empty>
      <p class="person-empty" role="status">{{ loading ? '正在加载人员…' : error || (keyword.trim() ? '没有匹配的人员' : '暂无有效的制作平台使用者') }}</p>
    </template>
    <template v-if="hasNext || error" #footer>
      <button type="button" class="person-more" :disabled="loading" @click="load(!error)">{{ error ? '重新加载' : loading ? '加载中…' : '加载更多人员' }}</button>
    </template>
  </ElSelect>
</template>
<style scoped>
.person-account,.person-status { color:var(--muted-foreground); font-size:12px; }
.person-status { margin-left:12px; }
.person-more { width:100%; padding:4px; font-size:13px; color:var(--foreground); }
.person-empty { padding:12px; margin:0; color:var(--muted-foreground); font-size:13px; }
</style>
