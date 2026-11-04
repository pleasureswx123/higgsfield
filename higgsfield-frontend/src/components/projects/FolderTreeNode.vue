<script setup lang="ts">
import { IconChevronRight, IconPlus, IconDotsVertical } from '@tabler/icons-vue'
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from '@/components/ui/collapsible'
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem } from '@/components/ui/dropdown-menu'
import FolderIcon from './FolderIcon.vue'
import type { Folder } from '@/api/folders'
defineProps<{
  counts?: Record<string, number>
  folder: Folder
  path: Folder[]
  children: Record<string, Folder[]>
  expanded: Set<string>
  currentId: string | null
  canWrite: boolean
  pending: boolean
  treeNext: Record<string, number>
  pinned: string[]
}>()
const emit = defineEmits<{
  navigate: [path: Folder[]]
  toggle: [folder: Folder]
  create: [parentId: string]
  edit: [folder: Folder]
  remove: [folder: Folder]
  move: [folder: Folder]
  copy: [folder: Folder]
  more: [parentId: string]
  pin: [id: string]
  moveUp: [value: { id: string; parentId: string | null }]
}>()
</script>
<template>
  <Collapsible as="li" :open="expanded.has(folder.id)" @update:open="emit('toggle', folder)">
    <div class="folder-tree-row" :class="{ active: currentId === folder.id }" :style="{ '--folder-depth': path.length }">
      <span class="folder-leading-icon" :class="{ 'can-expand': folder.hasChildren || children[folder.id]?.length }">
        <FolderIcon class="folder-default-icon" :size="24" :class="'folder-color-' + folder.color" />
        <CollapsibleTrigger v-if="folder.hasChildren || children[folder.id]?.length" as-child>
          <button
            class="folder-icon-button folder-expand-button"
            :aria-label="expanded.has(folder.id) ? '收起目录' : '展开目录'"
            :aria-expanded="expanded.has(folder.id)">
            <IconChevronRight :size="15" :class="{ rotated: expanded.has(folder.id) }" />
          </button>
        </CollapsibleTrigger>
      </span>
      <button class="folder-tree-label" @click="emit('navigate', [...path, folder])">
        <span>{{ folder.name }}</span>
      </button>
      <span class="folder-asset-count" title="当前文件夹内的素材数">{{ counts ? (counts[folder.id] ?? 0) : '—' }}</span>
      <button
        v-if="canWrite"
        class="folder-icon-button folder-hover-action"
        :disabled="pending"
        aria-label="新建子目录"
        @click="emit('create', folder.id)"
      >
        <IconPlus :size="15" />
      </button>
      <DropdownMenu>
        <DropdownMenuTrigger as-child><button class="folder-icon-button folder-hover-action" aria-label="文件夹操作"><IconDotsVertical :size="16" /></button></DropdownMenuTrigger>
        <DropdownMenuContent side="right" align="start" class="folder-dropdown-menu">
          <DropdownMenuItem v-if="canWrite" :disabled="pending" @select="emit('edit', folder)">编辑名称与颜色</DropdownMenuItem>
          <DropdownMenuItem v-if="canWrite" :disabled="pending" @select="emit('move', folder)">移动到…</DropdownMenuItem>
          <DropdownMenuItem v-if="canWrite" :disabled="pending" @select="emit('copy', folder)">复制到…</DropdownMenuItem>
          <DropdownMenuItem @select="emit('pin', folder.id)">{{ pinned.includes(folder.id) ? '取消置顶' : '置顶' }}</DropdownMenuItem>
          <DropdownMenuItem @select="emit('moveUp', { id: folder.id, parentId: path.at(-1)?.id || null })">上移</DropdownMenuItem>
          <DropdownMenuItem v-if="canWrite" :disabled="pending" @select="emit('remove', folder)">移至回收站</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
    <CollapsibleContent as="ul" class="folder-tree-children">
      <FolderTreeNode
        v-for="child in children[folder.id] || []"
        :key="child.id"
        :folder="child"
        :counts="counts"
        :path="[...path, folder]"
        :children="children"
        :expanded="expanded"
        :current-id="currentId"
        :can-write="canWrite"
        :pending="pending"
        :tree-next="treeNext"
        :pinned="pinned"
        @navigate="emit('navigate', $event)"
        @toggle="emit('toggle', $event)"
        @create="emit('create', $event)"
        @edit="emit('edit', $event)" @remove="emit('remove', $event)"
        @move="emit('move', $event)" @copy="emit('copy', $event)"
        @more="emit('more', $event)"
        @pin="emit('pin', $event)"
        @move-up="emit('moveUp', $event)"
      />
      <li v-if="treeNext[folder.id]">
        <button class="folder-text-button" @click="emit('more', folder.id)">加载更多</button>
      </li>
    </CollapsibleContent>
  </Collapsible>
</template>

<style scoped>
/* 图标与展开按钮共用位置，切换交互状态时名称不跳动。 */
.folder-leading-icon { position:relative; display:grid; place-items:center; flex:0 0 28px; width:28px; height:28px; }
.folder-expand-button { position:absolute; inset:0; width:28px; height:28px; border-radius:9px; opacity:0; color:var(--muted-foreground); }
.folder-tree-row:is(:hover, :focus-within, :has(> .folder-hover-action[data-state="open"])) > .can-expand .folder-default-icon { opacity:0; }
.folder-tree-row:is(:hover, :focus-within, :has(> .folder-hover-action[data-state="open"])) > .can-expand .folder-expand-button { opacity:1; background:var(--surface-hover); }
.folder-tree-row:is(:hover, :focus-within, :has(> .folder-hover-action[data-state="open"])) > .folder-asset-count { display:none; }
.folder-expand-button:focus-visible { outline:2px solid var(--focus); outline-offset:-2px; }
</style>
