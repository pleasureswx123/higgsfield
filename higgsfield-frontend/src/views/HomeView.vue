<script setup lang="ts">
import { ref } from 'vue'
import { IconSparkles } from '@tabler/icons-vue'
import CreationComposer from '@/components/creation/CreationComposer.vue'
import Button from '@/components/ui/Button.vue'
import ProjectCreation from '@/components/projects/ProjectCreation.vue'
import RecentProjects from '@/components/projects/RecentProjects.vue'
import HomeCreationProjectDialog from '@/components/projects/HomeCreationProjectDialog.vue'
import { useHomeCreation } from '@/composables/useHomeCreation'
const {
  selectedProject,
  mode,
  prompt,
  dialog,
  projects,
  q,
  page,
  total,
  loading,
  saving,
  error,
  open,
  close,
  load,
  search,
  choose,
} = useHomeCreation(true)
const creation = ref<InstanceType<typeof ProjectCreation>>()
function switchProject() {
  if (!creation.value?.canSwitchProject) return
  selectedProject.value = null
  prompt.value = ''
  open()
}
</script>
<template>
  <div class="home-page">
    <section class="creation-section">
      <div class="studio-badge"><IconSparkles :size="16" /> HIGGSFIELD STUDIO</div>
      <h1>让你的故事，成为现实</h1>
      <p class="hero-caption">每一个想法，都值得被看见。</p>
      <div v-if="!selectedProject" class="home-composer">
        <CreationComposer v-model:prompt="prompt" :kind="mode" project-required :disabled="saving" @kind="mode = $event" @project="open" />
      </div>
      <section v-if="selectedProject" class="home-creation-workspace">
        <div class="section-heading"><h2>{{ selectedProject.name }}</h2>
          <Button variant="ghost" :disabled="!creation?.canSwitchProject" @click="switchProject">切换项目</Button>
          <RouterLink :to="{ path: `/projects/${selectedProject.id}`, query: { tab: 'folders' } }">进入项目目录</RouterLink>
        </div>
        <p v-if="!creation?.canSwitchProject" class="muted">切换项目之前，请先保存当前草稿并等待操作完成。</p>
        <ProjectCreation ref="creation" :key="selectedProject.id" :project-id="selectedProject.id" :initial-prompt="prompt" :initial-kind="mode" />
      </section>
      <p v-else class="draft-note">描述暂存于当前会话，页面与主题切换会保留；刷新或退出登录前，请选择项目保存为草稿。</p>
    </section>
    <RecentProjects />
    <HomeCreationProjectDialog
      v-if="dialog"
      v-model:q="q"
      v-model:page="page"
      :projects="projects"
      :total="total"
      :loading="loading"
      :saving="saving"
      :error="error"
      @close="close"
      @search="search"
      @load="load"
      @choose="choose"
    />
  </div>
</template>

<style scoped>
.home-composer { margin:38px auto 0; width:100%; max-width:1000px; }
.home-creation-workspace { text-align: left; margin: 24px auto; max-width: 1000px; }
</style>
