<script setup>
import { computed, ref } from 'vue'
import useUserStore from '@/store/modules/user'
import ModelProfileEditor from './ModelProfileEditor.vue'
import ModelVersionEditor from './ModelVersionEditor.vue'
import ModelVariantEditor from './ModelVariantEditor.vue'
import { useModels } from '@/composables/studio/useModels'
import ModelVersionActions from './ModelVersionActions.vue'
import useSettingsStore from '@/store/modules/settings'
const settings = useSettingsStore()
const user = useUserStore()
const profileEditor = ref()
const versionEditor = ref()
const canWrite = computed(
  () => user.permissions.includes('*:*:*') || user.permissions.includes('model:write')
)
const {
  filters,
  formRef,
  model,
  version,
  models,
  versions,
  variants,
  search,
  load,
  loadVersions,
  selectModel,
  selectVersion,
  loadVariants,
} = useModels()
const states = {
  draft: '草稿（未验证）',
  verified: '已验证（未发布）',
  published: '已发布',
  disabled: '已停用',
}
const rules = {
  connectionId: [{ pattern: /^[1-9]\d{0,18}$/, message: '请输入有效连接ID', trigger: 'blur' }],
}
</script>
<template>
  <div class="app-container">
    <ModelVersionEditor
      ref="versionEditor"
      @saved="loadVersions"
    />
    <ModelProfileEditor
      ref="profileEditor"
      @saved="load"
    />
    <div class="heading">
      <h2>模型能力</h2>
      <el-button
        v-if="canWrite"
        type="primary"
        @click="profileEditor.start(filters.connectionId)"
        >登记模型身份</el-button
      >
      <el-button @click="settings.toggleTheme()">{{
        settings.isDark ? '切换亮色' : '切换暗色'
      }}</el-button>
    </div>
    <el-form
      ref="formRef"
      :model="filters"
      :rules="rules"
      inline
      label-position="top"
    >
      <el-form-item
        label="供应商连接ID"
        prop="connectionId"
        ><el-input
          v-model="filters.connectionId"
          clearable
      /></el-form-item>
      <el-form-item label="模型类型"
        ><el-select
          v-model="filters.kind"
          clearable
          ><el-option
            label="图片"
            value="image" /><el-option
            label="视频"
            value="video" /></el-select
      ></el-form-item>
      <el-form-item label="操作"
        ><el-button
          type="primary"
          :loading="models.loading"
          @click="search"
          >查询</el-button
        ></el-form-item
      >
    </el-form>
    <el-alert
      v-if="models.error"
      :title="models.error"
      type="error"
      :closable="false"
    />
    <el-table
      v-loading="models.loading"
      :data="models.rows"
      empty-text="暂无模型身份"
    >
      <el-table-column
        prop="displayName"
        label="模型名称"
      /><el-table-column
        prop="code"
        label="稳定码"
      /><el-table-column
        prop="connectionId"
        label="连接ID"
      />
      <el-table-column label="类型"
        ><template #default="{ row }">{{
          row.kind === 'image' ? '图片' : '视频'
        }}</template></el-table-column
      >
      <el-table-column label="操作"
        ><template #default="{ row }"
          ><el-button
            link
            type="primary"
            @click="selectModel(row)"
            >能力版本</el-button
          ></template
        ></el-table-column
      >
    </el-table>
    <el-pagination
      v-if="models.total"
      v-model:current-page="models.page"
      :total="models.total"
      :page-size="20"
      layout="total, prev, pager, next"
      @current-change="load"
    />
    <section v-if="model">
      <h3>{{ model.displayName }} · 能力版本</h3>
      <el-button
        v-if="canWrite"
        type="primary"
        @click="versionEditor.start(model)"
        >新增能力版本</el-button
      >
      <p class="hint">
        登记模型或版本不代表已完成联调。制作端可用性还受发布状态、路由、价格和权限约束。
      </p>
      <el-alert
        v-if="versions.error"
        :title="versions.error"
        type="error"
        :closable="false"
      />
      <el-table
        v-loading="versions.loading"
        :data="versions.rows"
        empty-text="暂无能力版本"
      >
        <el-table-column
          prop="versionNo"
          label="版本号"
        /><el-table-column
          prop="gatewayAlias"
          label="网关别名"
        /><el-table-column
          prop="region"
          label="区域"
        />
        <el-table-column label="状态"
          ><template #default="{ row }">{{ states[row.status] }}</template></el-table-column
        >
        <el-table-column label="操作"
          ><template #default="{ row }"
            ><el-button
              link
              type="primary"
              @click="selectVersion(row)"
              >能力与规格</el-button
            ></template
          ></el-table-column
        >
      </el-table>
      <el-pagination
        v-if="versions.total"
        v-model:current-page="versions.page"
        :total="versions.total"
        :page-size="20"
        layout="total, prev, pager, next"
        @current-change="loadVersions"
      />
    </section>
    <el-alert
      v-if="variants.error"
      :title="variants.error"
      type="error"
      :closable="false"
    />
    <p
      v-if="variants.loading && !version"
      role="status"
    >
      正在读取能力详情…
    </p>
    <section v-if="version">
      <h3>版本 {{ version.versionNo }} · {{ states[version.status] }}</h3>
      <el-button
        v-if="canWrite && version.status === 'draft'"
        @click="versionEditor.start(model, version)"
        >编辑草稿能力</el-button
      >
      <ModelVersionActions
        :key="`${version.id}:${version.revision}`"
        :version="version"
        @saved="loadVersions"
      />
      <p>底层模型：{{ version.underlyingModelId || '未登记' }}</p>
      <p>联调证据：{{ version.verificationRef || '未登记' }}</p>
      <details>
        <summary>能力配置</summary>
        <pre>{{ JSON.stringify(version.capabilities, null, 2) }}</pre>
      </details>
      <h4>精确计价规格</h4>
      <ModelVariantEditor
        :key="`${version.id}:${version.revision}`"
        :version="version"
        @saved="loadVariants"
      />
      <el-table
        v-loading="variants.loading"
        :data="variants.rows"
        empty-text="暂无精确规格"
      >
        <el-table-column
          prop="id"
          label="规格ID"
        /><el-table-column
          prop="variantKey"
          label="规格键"
        />
        <el-table-column label="完整维度"
          ><template #default="{ row }"
            ><span class="dimensions">{{ JSON.stringify(row.dimensions) }}</span></template
          ></el-table-column
        >
      </el-table>
      <el-pagination
        v-if="variants.total"
        v-model:current-page="variants.page"
        :total="variants.total"
        :page-size="20"
        layout="total, prev, pager, next"
        @current-change="loadVariants"
      />
    </section>
  </div>
</template>
<style scoped>
.heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}
.el-select,
.el-input {
  width: 200px;
}
section,
.el-pagination {
  margin-top: 20px;
}
.hint {
  color: var(--el-text-color-secondary);
}
pre {
  overflow: auto;
  padding: 12px;
  border: 1px solid var(--el-border-color);
  background: var(--el-fill-color-light);
}
.dimensions {
  overflow-wrap: anywhere;
}
</style>
