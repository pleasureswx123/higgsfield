<script setup lang="ts">
import { computed, watch, ref, nextTick, onBeforeUnmount } from 'vue'
import 'element-plus/theme-chalk/el-tree.css'
import { ElTree, ElInput } from 'element-plus'
import type { Folder, FolderKind } from '@/api/folders'
import { useDestinationTree } from '@/composables/useDestinationTree'
import FolderIcon from './FolderIcon.vue'
import Button from '@/components/ui/Button.vue'
const props = withDefaults(defineProps<{ projectId: string; kind?: FolderKind; path: Folder[]; disabled?: boolean; excludeId?: string; operation?: 'move' | 'copy' }>(), { kind: 'media', operation: 'move' })
const emit = defineEmits<{ select: [path: Folder[]]; busy: [value: boolean] }>()
const { query, searching, busy, error, results, treeKey, load, search, choose, reload, expanded } = useDestinationTree(props.projectId, props.kind, () => props.excludeId, () => !!props.disabled, path => emit('select', path))
watch(busy, value => emit('busy', value))
onBeforeUnmount(() => emit('busy', false))
const selected = computed(() => props.path.at(-1)?.id || 'root')
const tree = ref<InstanceType<typeof ElTree>>()
const searchTree = ref<InstanceType<typeof ElTree>>()
async function selectNode(value: Parameters<typeof choose>[0]) {
  await choose(value)
  await nextTick()
  tree.value?.setCurrentKey(selected.value)
  searchTree.value?.setCurrentKey(selected.value)
}
watch(() => props.path, async path => {
  await nextTick()
  // 新建目录后补入当前已加载的分支，让高亮和底部路径一致。
  for (let index = 0; index < path.length; index++) {
    const folder = path[index]!, parentId = index ? path[index - 1]!.id : 'root'
    if (!tree.value?.getNode(folder.id) && tree.value?.getNode(parentId)?.loaded) {
      tree.value.append({ id: folder.id, name: folder.name, path: path.slice(0, index + 1), leaf: !folder.hasChildren, disabled: false }, parentId)
    }
  }
  tree.value?.setCurrentKey(selected.value)
}, { deep: true })
const treeProps = { label: 'name', children: 'children', isLeaf: 'leaf', disabled: 'disabled' }
</script>
<template>
  <div class="destination-picker">
    <div class="destination-tools">
      <ElInput v-model="query" placeholder="搜索项目内目录" aria-label="搜索目标目录" clearable :disabled="disabled || busy" @keyup.enter="search" @clear="search" />
      <Button variant="outline" :disabled="disabled || busy" @click="search">搜索</Button>
    </div>
    <p class="muted">箭头展开目录，点击名称选择目标。{{ searching ? '搜索结果保留完整层级，清空搜索恢复目录树。' : '' }}</p>
    <p v-if="busy" role="status">正在读取目录…</p>
    <div v-if="error" role="alert" class="project-error">{{ error }} <Button variant="ghost" :disabled="disabled || busy" @click="reload">重新加载</Button></div>
    <div class="destination-tree" :class="{ locked: disabled || busy }" :inert="disabled || busy">
      <ElTree ref="tree" v-show="!searching" :key="treeKey" :props="treeProps" node-key="id" lazy :load="load" :default-expanded-keys="expanded" :current-node-key="selected" highlight-current :expand-on-click-node="false" @node-click="selectNode">
        <template #default="{ data }"><span class="destination-node" :class="{ unavailable: data.disabled }"><FolderIcon :size="18" /><span>{{ data.name }}</span><small v-if="data.disabled">不能移入自身或子目录</small></span></template>
      </ElTree>
      <ElTree ref="searchTree" v-if="searching" :data="results" :props="treeProps" node-key="id" default-expand-all :current-node-key="selected" highlight-current :expand-on-click-node="false" empty-text="没有匹配目录" @node-click="selectNode">
        <template #default="{ data }"><span class="destination-node" :class="{ unavailable: data.disabled }"><FolderIcon :size="18" /><span>{{ data.name }}</span><small v-if="data.disabled">不可选择</small></span></template>
      </ElTree>
    </div>
    <div class="destination-selected" role="status" aria-live="polite">
      <div class="destination-caption">{{ operation === 'copy' ? '复制到' : '移动到' }}</div>
      <div class="destination-path"><span :class="{ 'destination-final': !path.length }">项目根目录</span><template v-for="(folder, index) in path" :key="folder.id"><span class="destination-separator" aria-hidden="true">/</span><span :class="{ 'destination-final': index === path.length - 1 }">{{ folder.name }}</span></template></div>
    </div>
  </div>
</template>
<style scoped>
.destination-tools { display:flex; flex-wrap:wrap; gap:8px; margin:12px 0; }
.destination-tools > .el-input { flex:1; min-width:180px; }
.destination-tree { max-height:300px; min-height:100px; overflow:auto; border:1px solid var(--el-border-color); border-radius:8px; padding:8px; }
.destination-tree :deep(.el-tree-node__content) { height:36px; border-radius:6px; }
.destination-node { display:flex; align-items:center; gap:8px; min-width:0; }
.destination-node > span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.unavailable, .locked { opacity:.55; }
.destination-selected { margin:14px 0 8px; padding:12px 14px; border:1px solid var(--el-border-color-lighter); border-radius:8px; background:var(--el-fill-color-light); }
.destination-caption { margin-bottom:6px; font-size:12px; color:var(--el-text-color-secondary); }
.destination-path { display:flex; flex-wrap:wrap; gap:4px 8px; line-height:1.6; color:var(--el-text-color-regular); }
.destination-path > span { min-width:0; overflow-wrap:anywhere; }
.destination-final { font-weight:600; color:var(--el-text-color-primary); }
.destination-separator { color:var(--el-text-color-placeholder); }
small { color:var(--el-text-color-secondary); }
</style>
