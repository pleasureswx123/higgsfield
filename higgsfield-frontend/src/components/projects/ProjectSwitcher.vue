<script setup lang="ts">
import { watch, ref } from 'vue'
import { useRouter } from 'vue-router'
import { IconFolder, IconSelector, IconCheck } from '@tabler/icons-vue'
import type { Project } from '@/api/projects'
import { projectStatusLabels } from '@/utils/projects'
import { useProjectFilter } from '@/composables/useProjectFilter'
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover'
import { Command, CommandInput, CommandList, CommandItem, CommandGroup } from '@/components/ui/command'
import StudioPagination from '@/components/ui/StudioPagination.vue'
import Button from '@/components/ui/Button.vue'
const props = defineProps<{ project: Project }>()
const router = useRouter()
const { opened, q, page, rows, total, loading, error, search, load } = useProjectFilter(() => true, () => {})
const switching = ref(false)
watch(q, search)
async function choose(project: Project) {
  if (switching.value) return
  if (project.id === props.project.id) { opened.value = false; return }
  switching.value = true
  try {
    // 通过路由切换，沿用现有草稿、简报等离开保护，不绕过业务校验。
    const failure = await router.push(`/projects/${project.id}`)
    if (!failure) opened.value = false
  } finally { switching.value = false }
}
</script>
<template>
  <Popover v-model:open="opened">
    <PopoverTrigger as-child>
      <Button variant="ghost" class="project-switcher" aria-label="切换项目" :disabled="switching">
        <IconFolder :size="18" /><span class="project-switcher-name"><small>当前项目</small><strong :title="project.name">{{ project.name }}</strong></span><span class="project-switcher-status">{{ projectStatusLabels[project.status] }}</span><IconSelector :size="15" />
      </Button>
    </PopoverTrigger>
    <PopoverContent align="start" class="project-switcher-popover">
      <Command>
        <CommandInput placeholder="搜索项目…" aria-label="搜索切换项目" @update:model-value="q = String($event)" />
        <p v-if="loading" class="project-switcher-message" role="status">正在加载项目…</p>
        <p v-else-if="error" class="project-switcher-message" role="alert">{{ error }}<Button variant="ghost" @click="load">重试</Button></p>
        <CommandList v-else aria-label="可切换项目">
          <CommandGroup>
          <CommandItem v-for="item in rows" :key="item.id" :value="item.id" :disabled="switching" class="project-switcher-option" @select="choose(item)"><IconFolder :size="16" /><span>{{ item.name }}</span><IconCheck v-if="item.id === project.id" :size="16" aria-label="当前项目" /></CommandItem>
          </CommandGroup>
          <p v-if="!rows.length" class="project-switcher-message">没有匹配的可访问项目</p>
        </CommandList>
      </Command>
      <StudioPagination v-if="total > 10" v-model:current-page="page" :total="total" :page-size="10" />
      <Button as-child variant="ghost" class="project-switcher-all"><RouterLink to="/projects" @click="opened = false">查看全部项目</RouterLink></Button>
    </PopoverContent>
  </Popover>
</template>
<style scoped>
.project-switcher.ui-button { width:100%; height:auto; min-height:54px; padding:8px; gap:8px; margin-bottom:8px; border:1px solid var(--border); border-radius:10px; background:var(--surface); }
.project-switcher-name { flex:1; min-width:0; text-align:left; display:flex; flex-direction:column; gap:3px; }
.project-switcher-name small { color:var(--muted-foreground); font-size:10px; font-weight:400; }
.project-switcher-name strong { overflow:hidden; text-overflow:ellipsis; font-size:13px; }
.project-switcher-status { font-size:10px; color:var(--muted-foreground); font-weight:400; }
</style>
<style>
.project-switcher-popover { z-index:2100; width:280px; max-width:calc(100vw - 32px); padding:6px; background:var(--surface); color:var(--foreground); border:1px solid var(--border); border-radius:12px; }
.project-switcher-popover [cmdk-input-wrapper] { border-bottom:1px solid var(--border); }
.project-switcher-popover input { border:0; color:var(--foreground); background:transparent; box-shadow:none; min-width:0; font-size:13px; }
.project-switcher-option { padding:10px 8px; gap:8px; cursor:pointer; font-size:13px; }
.project-switcher-option > span { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.project-switcher-option[data-highlighted] { background:var(--surface-hover); }
.project-switcher-message { padding:12px 8px; margin:0; color:var(--muted-foreground); font-size:12px; }
.project-switcher-all.ui-button { width:100%; justify-content:flex-start; margin-top:4px; border-top:1px solid var(--border); border-radius:0; font-size:12px; }
</style>
