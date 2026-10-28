<script setup>
import { computed, ref, watch, onDeactivated } from 'vue'
import useUserStore from '@/store/modules/user'
import PriceBookEditor from './PriceBookEditor.vue'
import ExchangeRates from './ExchangeRates.vue'
import PricePublish from './PricePublish.vue'
import PriceActivationEnd from './PriceActivationEnd.vue'
import PriceSimulation from './PriceSimulation.vue'
import PriceSourceEditor from './PriceSourceEditor.vue'
import PriceSourceEvidence from './PriceSourceEvidence.vue'
import PriceVersionEditor from './PriceVersionEditor.vue'
import { usePrices } from '@/composables/studio/usePrices'
import useSettingsStore from '@/store/modules/settings'
const settings = useSettingsStore()
const user = useUserStore()
const editor = ref()
const versionEditor = ref()
const publisher = ref()
const activationEnd = ref()
const canPublish = computed(
  () => user.permissions.includes('*:*:*') || user.permissions.includes('billing:price:publish')
)
const sourceEditor = ref()
const createdSourceId = ref('')
const canWrite = computed(
  () => user.permissions.includes('*:*:*') || user.permissions.includes('billing:price:write')
)
const {
  filters,
  books,
  versions,
  history,
  book,
  version,
  detailError,
  detailLoading,
  allowed,
  search,
  loadBooks,
  selectBook,
  loadVersions,
  selectVersion,
  loadHistory,
} = usePrices()
const units = { token: 'Token', image: '张', second: '秒', character: '字符' }
watch(canWrite, () => {
  createdSourceId.value = ''
})
onDeactivated(() => {
  createdSourceId.value = ''
})
</script>
<template>
  <div class="app-container">
    <header>
      <h2>价格管理</h2>
      <el-button
        text
        @click="settings.toggleTheme()"
        >切换主题</el-button
      >
    </header>
    <ExchangeRates />
    <PriceActivationEnd
      ref="activationEnd"
      @saved="loadHistory"
    />
    <PricePublish
      ref="publisher"
      @saved="loadVersions"
    />
    <PriceSourceEditor
      ref="sourceEditor"
      @saved="createdSourceId = $event.id"
    />
    <el-button
      v-if="canWrite"
      @click="sourceEditor.start()"
      >登记价格来源</el-button
    >
    <el-alert
      v-if="createdSourceId"
      :title="`来源已登记：${createdSourceId}。请将此ID填写到价格草稿的来源证据字段。`"
      type="success"
      @close="createdSourceId = ''"
    />
    <PriceBookEditor
      ref="editor"
      @saved="search"
    />
    <el-button
      v-if="canWrite"
      @click="editor.start(filters.modelVariantId)"
      >登记价格簿</el-button
    >
    <el-form
      inline
      @submit.prevent
    >
      <el-form-item label="规格ID"><el-input v-model="filters.modelVariantId" /></el-form-item>
      <el-form-item label="用途"
        ><el-select
          v-model="filters.purpose"
          clearable
          ><el-option
            label="平台价"
            value="platform" /><el-option
            label="采购价"
            value="procurement" /></el-select
      ></el-form-item>
      <el-form-item label="账号ID"><el-input v-model="filters.accountId" /></el-form-item>
      <el-form-item label="币种"
        ><el-input
          v-model="filters.currency"
          placeholder="例如 CNY"
      /></el-form-item>
      <el-form-item
        ><el-button
          :disabled="!allowed"
          :loading="books.loading"
          @click="search"
          >查询</el-button
        ></el-form-item
      >
    </el-form>
    <el-alert
      v-if="books.error"
      :title="books.error"
      type="error"
      :closable="false"
    />
    <el-table
      v-loading="books.loading"
      :data="books.rows"
      empty-text="暂无价格簿"
    >
      <el-table-column
        prop="id"
        label="ID"
      /><el-table-column
        prop="name"
        label="价格簿"
      /><el-table-column
        prop="modelVariantId"
        label="规格ID"
      />
      <el-table-column label="用途"
        ><template #default="{ row }">{{
          row.purpose === 'platform' ? '平台价' : '采购价'
        }}</template></el-table-column
      >
      <el-table-column
        prop="accountId"
        label="采购账号"
      /><el-table-column
        prop="currency"
        label="币种"
      />
      <el-table-column label="操作"
        ><template #default="{ row }"
          ><el-button
            text
            @click="selectBook(row)"
            >查看版本</el-button
          ></template
        ></el-table-column
      >
    </el-table>
    <el-pagination
      v-if="books.total"
      v-model:current-page="books.page"
      :total="books.total"
      :page-size="20"
      layout="total, prev, pager, next"
      @current-change="loadBooks"
    />
    <section v-if="book">
      <h3>{{ book.name }} · {{ book.currency }}</h3>
      <PriceVersionEditor
        ref="versionEditor"
        @saved="loadVersions"
      />
      <el-button
        v-if="canWrite"
        @click="versionEditor.start(book)"
        >新建价格草稿</el-button
      >
      <el-alert
        v-if="versions.error"
        :title="versions.error"
        type="error"
        :closable="false"
      />
      <el-table
        v-loading="versions.loading"
        :data="versions.rows"
      >
        <el-table-column
          prop="id"
          label="版本ID"
        /><el-table-column
          prop="versionNo"
          label="版本号"
        />
        <el-table-column label="状态"
          ><template #default="{ row }">{{
            row.status === 'draft' ? '草稿' : '已发布'
          }}</template></el-table-column
        >
        <el-table-column
          prop="calculationScale"
          label="计算小数位"
        />
        <el-table-column label="操作"
          ><template #default="{ row }"
            ><el-button
              text
              @click="selectVersion(row)"
              >查看分项与历史</el-button
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
    <section v-loading="detailLoading">
      <el-alert
        v-if="detailError"
        :title="detailError"
        type="error"
        :closable="false"
      />
      <template v-if="version">
        <h3>价格版本 {{ version.versionNo }} · {{ book.currency }}</h3>
        <el-button
          v-if="canPublish"
          :disabled="!!version.validationIssues.length"
          @click="publisher.start(version)"
          >发布生效区间</el-button
        >
        <el-button
          v-if="canWrite && version.status === 'draft'"
          @click="versionEditor.start(book, version)"
          >编辑草稿</el-button
        >
        <p>已发布不代表当前生效。价格生效区间及变更记录见下方历史；不同币种不合计。</p>
        <el-alert
          v-for="(issue, i) in version.validationIssues"
          :key="i"
          :title="`${issue.path}：${issue.message}`"
          type="warning"
          :closable="false"
        />
        <el-table :data="version.items">
          <el-table-column
            prop="itemCode"
            label="计价分项"
          /><el-table-column label="单位"
            ><template #default="{ row }">{{
              units[row.unit] || row.unit
            }}</template></el-table-column
          >
          <el-table-column
            prop="unitQuantity"
            label="单价基数"
          /><el-table-column
            prop="unitPrice"
            label="单价"
          /><el-table-column
            prop="quantityFrom"
            label="阶梯起点"
          />
          <el-table-column label="阶梯上限"
            ><template #default="{ row }">{{
              row.quantityTo ?? '无上限'
            }}</template></el-table-column
          >
          <el-table-column label="公式"
            ><template #default="{ row }">{{
              row.formulaTemplate === 'linear' ? '线性' : '阶梯'
            }}</template></el-table-column
          ><el-table-column
            prop="freeReason"
            label="免费依据"
          />
        </el-table>
        <p>
          来源证据ID：{{ version.sourceIds.join('、') || '尚未绑定' }}；舍入方式：{{
            version.roundingMode
          }}。
        </p>
        <PriceSourceEvidence
          :key="`${version.id}:${version.revision}`"
          :source-ids="version.sourceIds"
        />
        <PriceSimulation
          :key="`simulation:${version.id}:${version.revision}`"
          :version-id="version.id"
        />
        <h4>发布与生效区间变更历史</h4>
        <el-button
          text
          :loading="history.loading"
          @click="loadHistory"
          >刷新历史</el-button
        >
        <el-alert
          v-if="history.error"
          :title="history.error"
          type="error"
          :closable="false"
        />
        <el-table
          v-loading="history.loading"
          :data="history.rows"
        >
          <el-table-column
            prop="createTime"
            label="时间"
          /><el-table-column
            prop="actorId"
            label="操作人ID"
          />
          <el-table-column label="操作"
            ><template #default="{ row }">{{
              row.action === 'publish'
                ? '发布'
                : row.action === 'end_activation'
                  ? '结束区间'
                  : row.action
            }}</template></el-table-column
          ><el-table-column
            prop="reason"
            label="原因"
          />
          <el-table-column label="区间操作"
            ><template #default="{ row }"
              ><el-button
                v-if="canPublish && row.diff?.after?.id"
                text
                @click="activationEnd.start(row.diff.after)"
                >结束此区间</el-button
              ></template
            ></el-table-column
          >
          <el-table-column label="区间变更证据"
            ><template #default="{ row }"
              ><details>
                <summary>查看记录</summary>
                <pre>{{ JSON.stringify(row.diff, null, 2) }}</pre>
              </details></template
            ></el-table-column
          >
        </el-table>
        <el-pagination
          v-if="history.total"
          v-model:current-page="history.page"
          :total="history.total"
          :page-size="20"
          layout="total, prev, pager, next"
          @current-change="loadHistory"
        />
      </template>
    </section>
  </div>
</template>
<style scoped>
header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.el-input,
.el-select {
  width: 180px;
}
section,
.el-pagination {
  margin-top: 20px;
}
.el-alert {
  margin-bottom: 12px;
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: var(--el-text-color-primary);
  background: var(--el-fill-color-light);
  padding: 12px;
}
</style>
