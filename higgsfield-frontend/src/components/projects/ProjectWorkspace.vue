<script setup lang="ts">
import type { ElementRecord } from '@/api/elements'
import type { Project } from '@/api/projects'
import { ref, watch } from 'vue'
import { IconChevronLeft, IconFolder, IconFileText, IconAdjustmentsHorizontal, IconAt, IconPhotoVideo, IconSparkles } from '@tabler/icons-vue'
import { useRoute } from 'vue-router'
import { useProjectWorkspace } from '@/composables/useProjectWorkspace'
import { formatProjectDate } from '@/utils/projects'
import BriefEditor from './BriefEditor.vue'
import BriefPreview from './BriefPreview.vue'
import ProjectMembers from './ProjectMembers.vue'
import ProjectFolders from './ProjectFolders.vue'
import ProjectElements from './ProjectElements.vue'
import ProjectCreation from './ProjectCreation.vue'
import GenerationCollection from './GenerationCollection.vue'
import UsageSummaryPanel from './UsageSummaryPanel.vue'
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
    'brief' | 'members' | 'folders' | 'elements' | 'creation' | 'generations' | 'usage'
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
      <button class="nav-link" @click="tab = 'brief'"><span class="project-nav-icon"><IconFileText :size="17" aria-hidden="true" /></span><span>项目简报</span></button>
      <button v-if="canReadMembers" class="nav-link" @click="tab = 'members'"><span class="project-nav-icon"><IconAdjustmentsHorizontal :size="17" aria-hidden="true" /></span><span>项目成员与设置</span></button>
      <button v-if="brief?.allowedActions.includes('element:read')" class="nav-link" @click="tab = 'elements'"><span class="project-nav-icon"><IconAt :size="17" aria-hidden="true" /></span><span>项目元素</span></button>
      <button v-if="brief?.allowedActions.includes('generation:read')" class="nav-link" @click="tab = 'generations'"><span class="project-nav-icon"><IconPhotoVideo :size="17" aria-hidden="true" /></span><span>项目生成</span></button>
      <button v-if="brief?.allowedActions.includes('generation:create')" class="nav-link" @click="tab = 'creation'"><span class="project-nav-icon"><IconSparkles :size="17" aria-hidden="true" /></span><span>开始创作</span></button>
    </div>
  </Teleport>
  <nav v-show="tab !== 'folders' && tab !== 'creation'" class="workspace-tabs" aria-label="项目详情导航">
    <button
      v-if="brief?.allowedActions.includes('project:usage:read')"
      :class="{ active: tab === 'usage' }"
      @click="tab = 'usage'"
    >
      项目用量
    </button>
    <button
      v-if="brief?.allowedActions.includes('generation:read')"
      :class="{ active: tab === 'generations' }"
      @click="tab = 'generations'"
    >
      项目生成
    </button>
    <button
      v-if="brief?.allowedActions.includes('generation:create')"
      :class="{ active: tab === 'creation' }"
      @click="tab = 'creation'"
    >
      开始创作
    </button>
    <button
      v-if="brief?.allowedActions.includes('element:read')"
      :class="{ active: tab === 'elements' }"
      @click="tab = 'elements'"
    >
      项目元素
    </button>
    <button
      v-if="brief?.allowedActions.includes('asset:read')"
      :class="{ active: tab === 'folders' }"
      @click="tab = 'folders'"
    >
      素材目录
    </button>
    <button :class="{ active: tab === 'brief' }" @click="tab = 'brief'">
      项目简报 <span v-if="dirty">·</span></button
    ><button v-if="canReadMembers" :class="{ active: tab === 'members' }" @click="tab = 'members'">
      项目成员
    </button>
  </nav>
  <div v-show="tab === 'brief' || tab === 'members'" class="brief-actions">
    <Button v-if="brief?.allowedActions.includes('project:manage') && project.status === 'active'" variant="ghost" :disabled="saving"
      @click="lifecycle?.start(project, 'rename')">编辑项目名称</Button>
    <Button v-if="brief?.allowedActions.includes('project:manage') && project.status === 'active'" variant="ghost" :disabled="saving"
      @click="lifecycle?.start(project, 'pause')">暂停项目</Button>
    <Button v-if="brief?.allowedActions.includes('project:manage') && project.status === 'paused'" variant="ghost" :disabled="saving"
      @click="lifecycle?.start(project, 'resume')">恢复运行</Button>
    <Button v-if="brief?.allowedActions.includes('project:archive') && ['active', 'paused'].includes(project.status)" variant="ghost" :disabled="saving"
      @click="lifecycle?.start(project, 'archive')">归档项目</Button>
    <Button v-else-if="brief?.allowedActions.includes('project:archive') && project.status === 'archived'" variant="ghost" :disabled="saving"
      @click="lifecycle?.start(project, 'restore')">恢复项目</Button>
  </div>
  <ProjectLifecycleDialog ref="lifecycle" @changed="lifecycleChanged" />
  <UsageSummaryPanel
    v-if="brief?.allowedActions.includes('project:usage:read')"
    v-show="tab === 'usage'"
    :project-id="projectId"
    :active="tab === 'usage'"
  />
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
        <Button v-if="canEdit" variant="ghost" :disabled="saving" @click="editing = !editing">{{
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
  <ProjectMembers
    v-if="brief && canReadMembers"
    v-show="tab === 'members'"
    :project-id="projectId"
  />
  <ProjectFolders ref="folderWorkspace" @selection-change="selectedAssetCount = $event"
    v-if="brief?.allowedActions.includes('asset:read')"
    v-show="tab === 'folders'"
    :visible="route.params.id === projectId"
    sidebar
    :project-id="projectId"
    :project-actions="brief.allowedActions"
    :can-write="brief.allowedActions.includes('folder:write')"
    :can-upload="
      brief.allowedActions.includes('asset:upload') && brief.allowedActions.includes('asset:create')
    "
    :can-download="brief.allowedActions.includes('asset:download')"
    :can-generate="brief.allowedActions.includes('generation:create')"
    @create="tab = 'creation'"
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
