<script setup lang="ts">
import { IconChevronRight, IconFolder, IconPlus, IconDotsVertical } from '@tabler/icons-vue'
import type { Folder } from '@/api/folders'
defineProps<{
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
  <li>
    <div class="folder-tree-row" :class="{ active: currentId === folder.id }">
      <button
        class="folder-icon-button"
        :aria-label="expanded.has(folder.id) ? '收起目录' : '展开目录'"
        :aria-expanded="expanded.has(folder.id)"
        @click="emit('toggle', folder)"
      >
        <IconChevronRight :size="14" :class="{ rotated: expanded.has(folder.id) }" />
      </button>
      <button class="folder-tree-label" @click="emit('navigate', [...path, folder])">
        <IconFolder class="colored-folder-icon" :size="19" :class="'folder-color-' + folder.color" /><span>{{
          folder.name
        }}</span>
      </button>
      <button
        v-if="canWrite"
        class="folder-icon-button folder-hover-action"
        :disabled="pending"
        aria-label="新建子目录"
        @click="emit('create', folder.id)"
      >
        <IconPlus :size="15" />
      </button>
      <details class="folder-node-menu">
        <summary aria-label="文件夹操作"><IconDotsVertical :size="16" /></summary>
        <div class="folder-node-actions">
          <button v-if="canWrite" :disabled="pending" @click="emit('edit', folder)">编辑名称与颜色</button>
          <button v-if="canWrite" :disabled="pending" @click="emit('move', folder)">移动到…</button>
          <button v-if="canWrite" :disabled="pending" @click="emit('copy', folder)">复制到…</button>
          <button @click="emit('pin', folder.id)">{{ pinned.includes(folder.id) ? '取消置顶' : '置顶' }}</button>
          <button @click="emit('moveUp', { id: folder.id, parentId: path.at(-1)?.id || null })">上移</button>
          <button v-if="canWrite" :disabled="pending" @click="emit('remove', folder)">移至回收站</button>
        </div>
      </details>
    </div>
    <ul v-if="expanded.has(folder.id)" class="folder-tree-children">
      <FolderTreeNode
        v-for="child in children[folder.id] || []"
        :key="child.id"
        :folder="child"
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
    </ul>
  </li>
</template>
