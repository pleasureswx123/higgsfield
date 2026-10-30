<script setup lang="ts">
import type { ElementRecord } from '@/api/elements'
import type { Project } from '@/api/projects'
import { ref, watch } from 'vue'
import { IconChevronLeft, IconFolder, IconAdjustmentsHorizontal, IconAt, IconPhotoVideo, IconSparkles } from '@tabler/icons-vue'
import { useRoute } from 'vue-router'
import { useProjectWorkspace } from '@/composables/useProjectWorkspace'
import { formatProjectDate, projectStatusLabels } from '@/utils/projects'
import BriefEditor from './BriefEditor.vue'
import BriefPreview from './BriefPreview.vue'
import ProjectMembers from './ProjectMembers.vue'
import ProjectPermissions from './ProjectPermissions.vue'
import ProjectFolders from './ProjectFolders.vue'
import ProjectElements from './ProjectElements.vue'
import ProjectCreation from './ProjectCreation.vue'
import GenerationCollection from './GenerationCollection.vue'
import Button from '@/components/ui/Button.vue'
import ProjectLifecycleDialog from './ProjectLifecycleDialog.vue'
const props = defineProps<{ projectId: string; project: Project }>()
const emit = defineEmits<{ changed: [project: Project] }>()
const lifecycle = ref<InstanceType<typeof ProjectLifecycleDialog>>()
const {
  brief,
  draft,
  dirty,
  loading,
  error,
  saving,
  notice,
  canEdit,
  canReadMembers,
  reload,
  load,
  save,
} = useProjectWorkspace(props.projectId)
function lifecycleChanged(project: Project) {
  emit('changed', project)
  void load()
}
const tab = ref<
    'brief' | 'members' | 'permissions' | 'folders' | 'elements' | 'creation' | 'generations'
  >(
    useRoute().query.tab === 'generations'
      ? 'generations'
      : useRoute().query.tab === 'elements'
        ? 'elements'
        : useRoute().query.tab === 'folders'
          ? 'folders'
          : useRoute().query.tab === 'creation'
            ? 'creation'
            : 'brief',
  ),
  editing = ref(false)
const creation = ref<InstanceType<typeof ProjectCreation>>()
const permissionEpoch = ref(0)
function memberChanged() { permissionEpoch.value++; void load() }
const selectedAssetCount = ref(0)
const folderWorkspace = ref<InstanceType<typeof ProjectFolders>>()
const useError = ref('')
async function useElements(items: ElementRecord[], completed?: () => void) {
  useError.value = ''
  if (!brief.value?.allowedActions.includes('generation:create') || !creation.value) return
  if (await creation.value.useElements(items)) { completed?.(); tab.value = 'creation' }
  else useError.value = creation.value?.useError || '创作区正在处理其他操作，请稍后重试'
}
const route = useRoute()
watch(
  () => [route.params.id, route.query.tab],
  () => {
    if (route.params.id === props.projectId && route.query.tab === 'generations')
      tab.value = 'generations'
    if (route.params.id === props.projectId && route.query.tab === 'elements')
      tab.value = 'elements'
    if (route.params.id === props.projectId && route.query.tab === 'creation')
      tab.value = 'creation'
    if (route.params.id === props.projectId && route.query.tab === 'folders') tab.value = 'folders'
  },
)
</script>
<template>
  <Teleport :key="`project-navigation-${projectId}`" to="#project-sidebar-navigation">
    <div v-if="route.params.id === projectId" class="project-local-navigation" aria-label="当前项目导航">
      <RouterLink to="/projects" class="nav-link"><IconChevronLeft :size="16" aria-hidden="true" /><span>返回我的项目</span></RouterLink>
      <strong class="project-nav-name"><span class="project-nav-icon"><IconFolder :size="17" aria-hidden="true" /></span><span>{{ project.name }}</span></strong>
      <button class="nav-link" :class="{ active: tab === 'brief' || tab === 'members' || tab === 'permissions' }" :aria-current="tab === 'brief' || tab === 'members' || tab === 'permissions' ? 'page' : undefined" @click="tab = ['members', 'permissions'].includes(tab) ? tab : 'brief'"><span class="project-nav-icon"><IconAdjustmentsHorizontal :size="17" aria-hidden="true" /></span><span>项目设置<span v-if="dirty"> ·</span></span></button>
      <button v-if="brief?.allowedActions.includes('element:read')" class="nav-link" :class="{ active: tab === 'elements' }" @click="tab = 'elements'"><span class="project-nav-icon"><IconAt :size="17" aria-hidden="true" /></span><span>项目元素库</span></button>
      <button v-if="brief?.allowedActions.includes('generation:read')" class="nav-link" :class="{ active: tab === 'generations' }" @click="tab = 'generations'"><span class="project-nav-icon"><IconPhotoVideo :size="17" aria-hidden="true" /></span><span>项目生成记录</span></button>
      <button v-if="brief?.allowedActions.includes('generation:create')" class="nav-link" :class="{ active: tab === 'creation' }" @click="tab = 'creation'"><span class="project-nav-icon"><IconSparkles :size="17" aria-hidden="true" /></span><span>开始创作</span></button>
    </div>
  </Teleport>
  <nav v-show="tab === 'brief' || tab === 'members' || tab === 'permissions'" class="workspace-tabs" aria-label="项目设置子导航">
    <button :class="{ active: tab === 'brief' }" @click="tab = 'brief'">
      项目简报 <span v-if="dirty">·</span></button
    ><button v-if="canReadMembers" :class="{ active: tab === 'members' }" @click="tab = 'members'">
      项目成员
    </button>
    <button v-if="canReadMembers" :class="{ active: tab === 'permissions' }" @click="tab = 'permissions'">角色和权限</button>
  </nav>
  <div v-show="tab === 'brief' || tab === 'members' || tab === 'permissions'" class="project-management" aria-label="项目管理">
    <div class="project-management-summary">
      <span class="project-management-label">项目管理</span>
      <div class="project-management-title"><strong :title="project.name">{{ project.name }}</strong><span class="project-management-status">{{ projectStatusLabels[project.status] }}</span></div>
      <p class="muted">管理项目名称与运行状态；暂停或归档前需确认。</p>
    </div>
    <div class="project-management-actions">
    <Button v-if="brief?.allowedActions.includes('project:manage') && project.status === 'active'" variant="outline" :disabled="saving"
      @click="lifecycle?.start(project, 'rename')" title="修改项目显示名称">修改名称</Button>
    <Button v-if="brief?.allowedActions.includes('project:manage') && project.status === 'active'" variant="outline" :disabled="saving"
      @click="lifecycle?.start(project, 'pause')" title="暂停新的创作与编辑，已受理任务继续维护">暂停项目</Button>
    <Button v-if="brief?.allowedActions.includes('project:manage') && project.status === 'paused'" variant="outline" :disabled="saving"
      @click="lifecycle?.start(project, 'resume')">恢复运行</Button>
    <Button v-if="brief?.allowedActions.includes('project:archive') && ['active', 'paused'].includes(project.status)" variant="outline" :disabled="saving"
      @click="lifecycle?.start(project, 'archive')" title="将项目转为只读，保留已有内容">归档项目</Button>
    <Button v-else-if="brief?.allowedActions.includes('project:archive') && project.status === 'archived'" variant="outline" :disabled="saving"
      @click="lifecycle?.start(project, 'restore')">恢复项目</Button>
    </div>
  </div>
  <ProjectLifecycleDialog ref="lifecycle" @changed="lifecycleChanged" />
  <GenerationCollection
    v-if="brief?.allowedActions.includes('generation:read')"
    v-show="tab === 'generations'"
    :project-id="projectId"
    :active="tab === 'generations'"
  />
  <p v-if="useError" class="project-error" role="alert">{{ useError }}</p>
  <p v-if="loading" role="status">正在加载项目工作区…</p>
  <div v-if="error" class="project-error" role="alert">
    <p>{{ error }}</p>
    <Button variant="outline" :disabled="saving" @click="reload">重新加载</Button>
    <p v-if="dirty" class="muted">未保存正文仍保留在编辑区，请先复制需要保留的内容。</p>
  </div>
  <section v-if="brief" v-show="tab === 'brief'" class="project-brief-panel">
    <div class="workspace-section-heading">
      <div>
        <h2>项目简报</h2>
        <p class="muted">
          更新于 {{ formatProjectDate(brief.updateTime) }} <span v-if="dirty">· 有未保存修改</span>
        </p>
      </div>
      <div class="brief-actions">
        <Button v-if="canEdit" variant="outline" :disabled="saving" @click="editing = !editing">{{
          editing ? '预览' : '编辑简报'
        }}</Button
        ><Button v-if="canEdit && dirty" :disabled="saving" @click="save">{{
          saving ? '正在保存…' : '保存简报'
        }}</Button>
      </div>
    </div>
    <p v-if="notice && !dirty" role="status" class="muted">{{ notice }}</p>
    <BriefEditor v-if="editing" v-model="draft" :disabled="saving || !canEdit" /><BriefPreview
      v-else
      :body="draft"
    />
  </section>
  <ProjectPermissions v-if="brief && canReadMembers" v-show="tab === 'permissions'" :key="permissionEpoch" :project-id="projectId" @changed="load()" />
  <ProjectMembers
    v-if="brief && canReadMembers"
    v-show="tab === 'members'"
    :project-id="projectId"
    @changed="memberChanged"
  />
  <ProjectFolders @select="tab = 'folders'" ref="folderWorkspace" @selection-change="selectedAssetCount = $event"
    v-if="brief?.allowedActions.includes('asset:read')"
    v-show="tab === 'folders'"
    :visible="route.params.id === projectId"
    sidebar
    :navigation-active="tab === 'folders'"
    :project-id="projectId"
    :project-actions="brief.allowedActions"
    :can-write="brief.allowedActions.includes('folder:write')"
    :can-upload="
      brief.allowedActions.includes('asset:upload') && brief.allowedActions.includes('asset:create')
    "
    :can-download="brief.allowedActions.includes('asset:download')"
    :can-generate="brief.allowedActions.includes('generation:create')"
    @create="tab = 'creation'" @reference="(asset, kind) => creation?.useAsset(asset, kind)"
  />
  <ProjectElements
    :visible="tab === 'elements'"
    v-if="brief?.allowedActions.includes('element:read')"
    v-show="tab === 'elements'"
    :project-id="projectId"
    :actions="brief.allowedActions"
    :using="creation?.using"
    :use-error="useError"
    @use="useElements"
  />
  <ProjectCreation ref="creation" dock @assets-changed="folderWorkspace?.refreshAll()"
    v-if="brief?.allowedActions.includes('generation:create')"
    v-show="tab === 'creation' || (tab === 'folders' && !selectedAssetCount && route.query.folderView !== 'trash')"
    :project-id="projectId"
  />
</template>
