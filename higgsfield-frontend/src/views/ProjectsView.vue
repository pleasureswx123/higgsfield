<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElInput, ElSelect, ElOption, ElPagination, ElCheckbox } from 'element-plus'
import { IconFolderPlus, IconSearch } from '@tabler/icons-vue'
import { useProjects } from '@/composables/useProjects'
import { projectStatusLabels } from '@/utils/projects'
import ProjectCard from '@/components/projects/ProjectCard.vue'
import CreateProjectDialog from '@/components/projects/CreateProjectDialog.vue'
import ProjectPreferenceDialog from '@/components/projects/ProjectPreferenceDialog.vue'
import ProjectCollections from '@/components/projects/ProjectCollections.vue'
import ProjectViewPreference from '@/components/projects/ProjectViewPreference.vue'
import type { ProjectViewSettings } from '@/api/viewPreferences'
import Button from '@/components/ui/Button.vue'
const { rows, loading, error, total, page, search, status, sort, hidden, pinned, collectionId, load, applyFilters, canCreate } =
  useProjects()
const open = ref(false),
  router = useRouter()
const preferenceDialog = ref<InstanceType<typeof ProjectPreferenceDialog>>()
const hasFilters = computed(() => Boolean(search.value || status.value || hidden.value || pinned.value || collectionId.value))
const viewSettings = computed<ProjectViewSettings>(() => ({ sort: sort.value, status: status.value || null, hidden: hidden.value, pinned: pinned.value, collectionId: collectionId.value || null }))
function restoreView(value: ProjectViewSettings) {
  sort.value = value.sort; status.value = value.status || ''; hidden.value = value.hidden
  pinned.value = value.pinned; collectionId.value = value.collectionId || ''; applyFilters()
}
function created(id: string) {
  void router.push(`/projects/${id}`)
}
</script>
<template>
  <section class="projects-page">
    <div class="project-page-heading">
      <div>
        <h1>我的项目</h1>
        <p class="muted">组织你的故事、素材与团队。</p>
      </div>
      <Button v-if="canCreate" @click="open = true"><IconFolderPlus :size="18" />新建项目</Button>
    </div>
    <div class="project-toolbar">
      <ProjectCollections v-model="collectionId" @filter="applyFilters()" @changed="load" />
      <ElCheckbox v-model="hidden" @change="applyFilters()">查看已隐藏</ElCheckbox>
      <ElCheckbox v-model="pinned" @change="applyFilters()">仅置顶</ElCheckbox>
      <div class="project-filter">
        <span class="project-filter-label">项目状态</span
        ><ElSelect
          v-model="status"
          placeholder="全部项目"
          aria-label="项目状态"
          @change="applyFilters()"
          ><ElOption label="全部项目" value="" /><ElOption
            v-for="(label, value) in projectStatusLabels"
            :key="value"
            :label="label"
            :value="value"
        /></ElSelect>
      </div>
      <div class="project-search">
        <ElInput
          v-model="search"
          placeholder="搜索项目名称"
          maxlength="200"
          clearable
          aria-label="搜索项目名称"
          @keyup.enter="applyFilters()"
          @clear="applyFilters()"
          ><template #prefix><IconSearch :size="16" /></template></ElInput
        ><Button variant="ghost" @click="applyFilters()">搜索</Button>
      </div>
      <ElSelect v-model="sort" aria-label="项目排序" class="project-sort" @change="applyFilters()"
        ><ElOption label="最新创建" value="created_desc" /><ElOption
          label="最早创建"
          value="created_asc" /><ElOption label="名称排序" value="name_asc"
      /></ElSelect>
    </div>
    <ProjectViewPreference :settings="viewSettings" @restore="restoreView" />
    <div v-if="error" class="project-error" role="alert">
      <p>{{ error }}</p>
      <Button variant="outline" @click="load">重新加载</Button>
    </div>
    <div v-else-if="loading" class="project-loading" role="status">正在加载项目…</div>
    <template v-else
      ><div class="project-grid">
        <button v-if="canCreate" class="new-project-card" @click="open = true">
          <span><IconFolderPlus :size="32" /></span><strong>新建项目</strong></button
        ><div v-for="project in rows" :key="project.id" class="project-with-preferences">
          <ProjectCard :project="project" />
          <Button variant="ghost" @click="preferenceDialog?.start(project)">{{ project.preference?.isPinned ? '已置顶 · ' : '' }}个人偏好</Button>
        </div>
      </div>
      <div v-if="!rows.length" class="project-empty-note">
        <h2>{{ hasFilters ? '没有匹配的项目' : '你的故事，从第一个项目开始' }}</h2>
        <p>
          {{
            hasFilters
              ? '试试其他关键词、状态或个人导航筛选。'
              : canCreate
                ? '点击新建项目，创建专属的制作空间。'
                : '当前没有可见项目，请联系负责人添加成员权限。'
          }}
        </p>
      </div>
      <ElPagination
        v-if="total > 20"
        :current-page="page"
        :page-size="20"
        :total="total"
        layout="prev, pager, next, total"
        @current-change="applyFilters" /></template
    ><CreateProjectDialog v-model="open" @created="created" />
    <ProjectPreferenceDialog ref="preferenceDialog" @changed="load" />
  </section>
</template>
<style scoped>
.project-with-preferences { min-width: 0; display: flex; flex-direction: column; gap: 8px; }
.project-with-preferences > .project-card { flex: 1; }
</style>
