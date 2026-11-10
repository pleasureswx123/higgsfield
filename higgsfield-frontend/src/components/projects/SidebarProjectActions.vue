<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { IconDotsVertical, IconPin, IconPinFilled, IconPinnedOff, IconPencil, IconTrash, IconEye, IconEyeOff } from '@tabler/icons-vue'
import type { Project } from '@/api/projects'
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator } from '@/components/ui/dropdown-menu'
import Button from '@/components/ui/Button.vue'
import ProjectLifecycleDialog from './ProjectLifecycleDialog.vue'
import { useSidebarProjectActions } from '@/composables/useSidebarProjectActions'
import { useProjectUpdatesStore } from '@/stores/projectUpdates'
const props = defineProps<{ project: Project; restoreOnly?: boolean }>()
const lifecycle = ref<InstanceType<typeof ProjectLifecycleDialog>>()
const updates = useProjectUpdatesStore()
const { busy, checking, error, canEdit, retry, pinned, hidden, inspect, togglePin, toggleHidden } = useSidebarProjectActions(() => props.project)
async function selectPin() {
  await togglePin()
  if (error.value) ElMessage.error(`${error.value}；可重新打开项目菜单重试。`)
}
async function selectHidden() {
  await toggleHidden()
  if (error.value) ElMessage.error(`${error.value}；${props.restoreOnly ? '请点击按钮重试。' : '可重新打开项目菜单重试。'}`)
}
</script>
<template>
  <Button v-if="restoreOnly" variant="ghost" :disabled="busy || updates.orderLocked" @click="selectHidden"><IconEye :size="16" />{{ busy ? '正在恢复…' : retry ? '重试取消隐藏' : '取消隐藏' }}</Button>
  <DropdownMenu v-else :modal="false" @update:open="inspect">
    <DropdownMenuTrigger as-child>
      <Button variant="ghost" class="sidebar-project-more" :disabled="updates.orderLocked" :class="{ 'is-pinned': pinned }" :aria-label="`${project.name}${pinned ? '，已置顶，' : ' '}项目操作`">
        <IconPinFilled v-if="pinned" class="sidebar-project-pin" :size="14" aria-hidden="true" />
        <IconDotsVertical class="sidebar-project-dots" :size="17" aria-hidden="true" />
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="start" side="right" :side-offset="8" class="sidebar-project-actions">
      <DropdownMenuLabel>项目操作</DropdownMenuLabel>
      <DropdownMenuItem :disabled="busy" @select="selectPin"><component :is="pinned ? IconPinnedOff : IconPin" :size="18" />{{ busy ? '正在保存…' : retry ? '重试上次操作' : pinned ? '取消置顶' : '置顶' }}</DropdownMenuItem>
      <DropdownMenuItem :disabled="checking || !canEdit || busy || retry" @select="lifecycle?.start(project, 'rename')"><IconPencil :size="18" />编辑名称</DropdownMenuItem>
      <DropdownMenuItem :disabled="busy || retry" @select="selectHidden"><component :is="hidden ? IconEye : IconEyeOff" :size="18" />{{ hidden ? '取消隐藏' : '隐藏' }}</DropdownMenuItem>
      <p v-if="error" class="project-action-message" role="alert">{{ error }}</p>
      <DropdownMenuSeparator />
      <DropdownMenuItem disabled class="project-action-delete"><IconTrash :size="18" />删除</DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>
  <ProjectLifecycleDialog v-if="!restoreOnly" ref="lifecycle" @changed="updates.notify" />
</template>
<style>
.sidebar-project-more.ui-button { position:absolute; right:4px; top:5px; width:30px; height:30px; min-height:0; padding:0; border-radius:7px; color:var(--muted-foreground); }
.sidebar-project-more.ui-button:hover,.sidebar-project-more[data-state="open"] { color:var(--foreground); background:var(--surface-hover); }
.sidebar-project-more.is-pinned .sidebar-project-dots { display:none; }
.sidebar-project-list [data-sidebar="menu-item"]:is(:hover, :focus-within) .sidebar-project-more.is-pinned .sidebar-project-pin,
.sidebar-project-more.is-pinned[data-state="open"] .sidebar-project-pin { display:none; }
.sidebar-project-list [data-sidebar="menu-item"]:is(:hover, :focus-within) .sidebar-project-more.is-pinned .sidebar-project-dots,
.sidebar-project-more.is-pinned[data-state="open"] .sidebar-project-dots { display:block; }
.sidebar-project-actions .project-action-delete { color:var(--destructive); }
.project-action-message { margin:4px 8px; font-size:11px; line-height:1.5; color:var(--muted-foreground); }
</style>
