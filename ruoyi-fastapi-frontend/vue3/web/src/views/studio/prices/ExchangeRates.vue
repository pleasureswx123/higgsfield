<script setup>
import { ref } from 'vue'
import ExchangeRateEditor from './ExchangeRateEditor.vue'
const editor = ref()
import { useExchangeRates } from '@/composables/studio/useExchangeRates'
import PriceSourceEvidence from './PriceSourceEvidence.vue'
const {
  allowed,
  open,
  selected,
  rows,
  total,
  page,
  loading,
  error,
  filters,
  load,
  search,
  select,
} = useExchangeRates()
</script>
<template>
  <section>
    <ExchangeRateEditor
      ref="editor"
      @saved="search"
    />
    <el-button
      text
      :disabled="!allowed"
      @click="open = !open"
      >{{ open ? '收起汇率版本' : '查看汇率版本' }}</el-button
    >
    <template v-if="open">
      <el-button
        v-if="editor?.canCreate"
        @click="editor.start()"
        >登记汇率草稿</el-button
      >
      <p>
        汇率为人工登记的版本，不是实时市场报价。1单位基准币兑换对应数量的报价币；用于试算时需明确填写版本ID，已发布不代表当前仍在有效期内。
      </p>
      <el-form
        inline
        @submit.prevent
      >
        <el-form-item label="基准币"
          ><el-input
            v-model="filters.baseCurrency"
            placeholder="例如 USD"
        /></el-form-item>
        <el-form-item label="报价币"
          ><el-input
            v-model="filters.quoteCurrency"
            placeholder="例如 CNY"
        /></el-form-item>
        <el-form-item
          ><el-button
            :loading="loading"
            @click="search"
            >查询</el-button
          ></el-form-item
        >
      </el-form>
      <el-alert
        v-if="error"
        :title="error"
        type="error"
        :closable="false"
      />
      <el-table
        v-loading="loading"
        :data="rows"
        empty-text="暂无汇率版本"
      >
        <el-table-column
          prop="id"
          label="版本ID"
        /><el-table-column
          prop="baseCurrency"
          label="基准币"
        /><el-table-column
          prop="quoteCurrency"
          label="报价币"
        /><el-table-column
          prop="rate"
          label="汇率"
        />
        <el-table-column label="状态"
          ><template #default="{ row }">{{
            row.status === 'draft' ? '草稿' : '已发布'
          }}</template></el-table-column
        >
        <el-table-column
          prop="validFrom"
          label="生效起点"
        /><el-table-column label="生效终点"
          ><template #default="{ row }">{{
            row.validUntil || '无结束时间'
          }}</template></el-table-column
        >
        <el-table-column label="操作"
          ><template #default="{ row }"
            ><el-button
              text
              @click="select(row)"
              >查看来源</el-button
            ><el-button
              v-if="editor?.canPublish && row.status === 'draft'"
              text
              @click="editor.start(row)"
              >发布</el-button
            ></template
          ></el-table-column
        >
      </el-table>
      <el-pagination
        v-if="total"
        v-model:current-page="page"
        :page-size="20"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="load"
      />
      <PriceSourceEvidence
        v-if="selected"
        :key="selected.id"
        :source-ids="[selected.sourceId]"
      />
    </template>
  </section>
</template>
