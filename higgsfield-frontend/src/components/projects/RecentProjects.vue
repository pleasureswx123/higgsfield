<script setup lang="ts">
import { useRouter } from 'vue-router'
import { ref } from 'vue'
import { IconFolderPlus, IconChevronRight } from '@tabler/icons-vue'
import { useProjects } from '@/composables/useProjects'
import ProjectCard from './ProjectCard.vue'
import CreateProjectDialog from './CreateProjectDialog.vue'
import Button from '@/components/ui/Button.vue'
const { rows, loading, error, canCreate, load } = useProjects(true)
const open = ref(false),
  router = useRouter()
function created(id: string) {
  void router.push({ name: 'project-detail', params: { id }, query: { tab: 'creation' } })
}
</script>
<template>
  <section class="projects-section">
    <div class="section-heading">
      <h2>我参与的项目</h2>
      <RouterLink v-if="rows.length" to="/projects">查看全部<IconChevronRight :size="16" /></RouterLink>
    </div>
    <p v-if="error" class="project-error" role="alert">
      {{ error }} <Button variant="ghost" @click="load">重试</Button>
    </p>
    <p v-else-if="loading" class="muted" role="status">正在加载项目…</p>
    <div v-else-if="!rows.length" class="project-onboarding">
      <div class="onboarding-icon" aria-hidden="true"><IconFolderPlus :size="30" /></div>
      <h2>{{ canCreate ? '从第一个项目开始创作' : '加入项目，开始团队创作' }}</h2>
      <p>{{ canCreate ? '用项目集中管理图片、视频与参考素材，也可以邀请团队成员一起制作。' : '当前没有可显示的项目，请联系管理员或项目负责人将你加入项目。' }}</p>
      <template v-if="canCreate">
        <ol aria-label="开始创作的步骤"><li>创建项目</li><li>准备素材与文件夹</li><li>开始生成图片或视频</li></ol>
        <Button @click="open = true"><IconFolderPlus :size="18" />创建项目</Button>
      </template>
      <RouterLink class="hidden-project-link" :to="{ path: '/projects', query: { hidden: 'true' } }">已有项目被隐藏？查看已隐藏的项目</RouterLink>
    </div>
    <div v-else class="project-grid">
      <button v-if="canCreate" class="new-project-card" @click="open = true">
        <span><IconFolderPlus :size="32" /></span><strong>新建项目</strong></button
      ><ProjectCard v-for="project in rows" :key="project.id" :project="project" />
    </div>
    <CreateProjectDialog v-model="open" @created="created" />
  </section>
</template>

<style scoped>
.project-onboarding { display:flex; flex-direction:column; align-items:center; text-align:center; padding:48px 24px; border:1px solid var(--border); border-radius:20px; background:var(--surface-raised); color:var(--foreground); }
.onboarding-icon { display:grid; place-items:center; width:64px; height:64px; margin-bottom:20px; border-radius:18px; background:color-mix(in srgb, var(--primary) 12%, transparent); color:var(--foreground); }
.project-onboarding h2 { margin:0 0 12px; font-size:24px; font-weight:600; }
.project-onboarding p { max-width:460px; margin:0; line-height:1.8; color:var(--muted-foreground); font-size:14px; }
.project-onboarding ol { display:flex; flex-wrap:wrap; justify-content:center; gap:12px 28px; padding:0; margin:24px 0; list-style:none; counter-reset:step; color:var(--muted-foreground); font-size:12px; }
.project-onboarding li { counter-increment:step; display:flex; align-items:center; gap:8px; }
.project-onboarding li::before { content:counter(step); display:grid; place-items:center; width:22px; height:22px; border:1px solid var(--border); border-radius:50%; }
.hidden-project-link { margin-top:24px; font-size:12px; color:var(--muted-foreground); text-underline-offset:4px; }
.hidden-project-link:hover { color:var(--foreground); text-decoration:underline; }
@media (max-width:600px) { .project-onboarding { padding:32px 16px; } .project-onboarding h2 { font-size:20px; } }
</style>
