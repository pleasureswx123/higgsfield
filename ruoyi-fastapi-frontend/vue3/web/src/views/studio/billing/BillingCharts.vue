<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart, ScatterChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, DataZoomComponent, TitleComponent, AriaComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import useSettingsStore from '@/store/modules/settings'
import { billingChartPoints, sumBillingAmounts, billingAnalysisData } from '@/utils/billingCharts'

echarts.use([BarChart, LineChart, PieChart, ScatterChart, GridComponent, TooltipComponent, DataZoomComponent, TitleComponent, AriaComponent, CanvasRenderer])
const props = defineProps({ summary: Object, groupBy: String, timeRange: Array })
const settings = useSettingsStore()
const currency = ref(''), canvas = ref(), showData = ref(false)
const analysis = ref('compare')
const chartKind = computed(() => props.groupBy === 'user' ? analysis.value : 'trend')
const chartTitle = computed(() => chartKind.value === 'share' ? '人员费用占比' : chartKind.value === 'relationship' ? '人员任务数与费用关系' : labels[props.groupBy])
const currencies = computed(() => [...new Set((props.summary?.rows || []).map(row => row.currency))])
const rows = computed(() => (props.summary?.rows || []).filter(row => row.currency === currency.value))
const points = computed(() => billingChartPoints(rows.value, props.groupBy, props.timeRange))
const total = computed(() => sumBillingAmounts(rows.value))
const disputed = computed(() => sumBillingAmounts(rows.value, 'disputedAmount'))
const unknown = computed(() => rows.value.reduce((sum, row) => sum + BigInt(row.unknownCount || 0), 0n).toString())
const labels = { user: '人员费用对比', day: '每日费用趋势', week: '每周费用趋势', month: '每月费用趋势' }
const money = value => Number(value || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
const usage = (value, missing) => `${BigInt(value || 0).toLocaleString('zh-CN')}${Number(missing) > 0 ? '（部分已记录）' : ''}`
let chart, observer
watch(currencies, values => { if (!values.includes(currency.value)) currency.value = values[0] || '' }, { immediate: true })
async function render() {
  await nextTick()
  if (!canvas.value || !rows.value.length || !canvas.value.clientWidth) return
  chart ||= echarts.init(canvas.value)
  const style = getComputedStyle(canvas.value)
  const text = style.getPropertyValue('--el-text-color-regular').trim()
  const line = style.getPropertyValue('--el-border-color-lighter').trim()
  const color = style.getPropertyValue('--el-color-primary').trim()
  const people = props.groupBy === 'user'
  if (chartKind.value === 'share' || chartKind.value === 'relationship') {
    const pie = chartKind.value === 'share'
    const data = billingAnalysisData(points.value, chartKind.value)
    chart.setOption({
      animation: false, aria: { enabled: true },
      color: [color, '#67a985', '#d3a44e', '#ab83c6', '#d37474', '#4c9eae'],
      title: { show: !data.length, text: data.length ? chartTitle.value : (pie ? '暂无可计算占比的已知费用' : '暂无费用完整的人员数据'), left: 'center', top: 'center', textStyle: { color: text, fontSize: 14 } },
      tooltip: { trigger: 'item', renderMode: 'richText', formatter: item => `${item.data.name}\n费用：${item.data.row.totalKnownAmount} ${currency.value}\n${pie ? `占已知费用：${item.percent}%` : `任务数：${item.value[0]}`}` },
      grid: pie ? undefined : { left: 30, right: 35, top: 40, bottom: 50, containLabel: true },
      xAxis: pie ? [] : { type: 'value', name: '任务数（次）', nameLocation: 'middle', nameGap: 30, minInterval: 1, max: value => Math.max(1, Math.ceil(value.max * 1.1)), axisLabel: { color: text }, nameTextStyle: { color: text }, splitLine: { lineStyle: { color: line } } },
      yAxis: pie ? [] : { type: 'value', name: `费用（${currency.value}）`, axisLabel: { color: text }, nameTextStyle: { color: text }, splitLine: { lineStyle: { color: line } } },
      series: [{ type: pie ? 'pie' : 'scatter', data, radius: pie ? '60%' : undefined, symbolSize: 14,
        label: { show: pie, color: text, formatter: '{b}\n{d}%' }, emphasis: { focus: 'self' } }],
    }, true)
    chart.resize()
    return
  }
  chart.setOption({
    animation: false,
    aria: { enabled: true },
    grid: { left: 24, right: 28, top: 24, bottom: points.value.length > 12 ? 75 : 35, containLabel: true },
    tooltip: { trigger: 'axis', renderMode: 'richText', formatter: items => {
      const row = points.value[items[0]?.dataIndex]
      return row ? `${row.displayName}\n已知费用：${row.totalKnownAmount} ${currency.value}\n待确认：${row.unknownCount || '0'} 笔` : ''
    } },
    xAxis: { type: 'category', data: points.value.map(row => row.displayName), axisLabel: { color: text, hideOverlap: true }, axisLine: { lineStyle: { color: line } } },
    yAxis: { type: 'value', axisLabel: { color: text }, splitLine: { lineStyle: { color: line } } },
    dataZoom: points.value.length > 12 ? [{ type: 'slider', startValue: people ? 0 : Math.max(0, points.value.length - 30), endValue: people ? Math.min(29, points.value.length - 1) : points.value.length - 1, textStyle: { color: text }, borderColor: line }] : [],
    series: [{ name: '已知费用', type: people ? 'bar' : 'line', barMaxWidth: 48, smooth: false, connectNulls: false,
      data: points.value.map(row => Number(row.totalKnownAmount) === 0 && BigInt(row.unknownCount || 0) > 0n ? null : Number(row.totalKnownAmount)),
      itemStyle: { color }, lineStyle: { color }, symbolSize: 7 }],
  }, true)
  chart.resize()
}
watch(() => [props.summary, props.groupBy, props.timeRange, currency.value, chartKind.value, settings.isDark, settings.theme], render, { deep: true })
onMounted(() => { observer = new ResizeObserver(() => chart?.resize()); observer.observe(canvas.value); void render() })
onBeforeUnmount(() => { observer?.disconnect(); chart?.dispose(); chart = undefined })
</script>
<template>
  <section class="billing-charts">
    <div class="chart-heading"><h3>{{ labels[groupBy] }}</h3><el-select v-model="currency" aria-label="图表币种" placeholder="暂无币种" style="width:120px"><el-option v-for="item in currencies" :key="item" :value="item" :label="item" /></el-select></div>
    <p class="hint">按上海时间统计；周一为每周起点。各币种独立展示，首尾周期仅统计所选时间范围。</p>
    <div v-if="rows.length" class="metrics">
      <div><span>已知费用合计 · {{ currency }}</span><strong :title="total">{{ money(total) }}</strong></div>
      <div v-if="groupBy === 'user'"><span>有费用记录的人员</span><strong>{{ rows.length }} 人</strong></div>
      <div v-else><span>其中争议金额 · {{ currency }}</span><strong :title="disputed">{{ money(disputed) }}</strong></div>
      <div><span>待确认费用</span><strong>{{ unknown }} 笔</strong></div>
    </div>
    <el-empty v-if="!rows.length" :description="summary ? '当前范围没有费用记录' : '请选择时间范围后查询'" />
    <template v-if="groupBy === 'user' && rows.length">
      <h3>人员消耗排行</h3>
      <p class="hint">按费用从高到低排列。任务数仅统计已有费用记录的任务；图片数量、视频 Token 为供应商记录的用量，未记录不代表零。费用显示保留最多四位小数，悬停可查看精确金额。</p>
      <el-table :data="points" class="people-table">
        <el-table-column type="index" label="排名" width="60" />
        <el-table-column label="人员" min-width="160"><template #default="{ row }"><div>{{ row.displayName }}</div><small>{{ row.userName }}</small></template></el-table-column>
        <el-table-column prop="imageTaskCount" label="图片任务" min-width="90" />
        <el-table-column prop="videoTaskCount" label="视频任务" min-width="90" />
        <el-table-column label="图片用量（张）" min-width="150"><template #default="{ row }">{{ row.imageTaskCount === row.imageUsageMissingCount && Number(row.imageTaskCount) > 0 ? '未记录' : usage(row.imageCount, row.imageUsageMissingCount) }}</template></el-table-column>
        <el-table-column label="视频用量（Token）" min-width="165"><template #default="{ row }">{{ row.videoTaskCount === row.videoUsageMissingCount && Number(row.videoTaskCount) > 0 ? '未记录' : usage(row.videoTokens, row.videoUsageMissingCount) }}</template></el-table-column>
        <el-table-column :label="`费用（${currency}）`" min-width="130"><template #default="{ row }"><strong :title="row.totalKnownAmount">{{ money(row.totalKnownAmount) }}</strong></template></el-table-column>
        <el-table-column prop="unknownCount" label="待确认（笔）" min-width="105" />
      </el-table>
      <p class="hint">费用含争议金额 {{ money(disputed) }} {{ currency }}；仅展示当前筛选范围内有费用记录的人员。</p>
    </template>
    <div v-if="rows.length" class="analysis-controls">
      <el-radio-group v-if="groupBy === 'user'" v-model="analysis" aria-label="分析方式">
        <el-radio-button value="compare">分类对比 · 柱状图</el-radio-button>
        <el-radio-button value="share">占比结构 · 饼图</el-radio-button>
        <el-radio-button value="relationship">变量关系 · 散点图</el-radio-button>
      </el-radio-group>
      <el-tag v-else>时间趋势 · 折线图</el-tag>
      <h3>{{ chartTitle }}</h3>
      <p v-if="chartKind === 'share'" class="hint">按人员展示当前币种的已知费用占比，不含待确认金额；零费用不绘制扇区。</p>
      <p v-if="chartKind === 'relationship'" class="hint">每个点代表一人：横轴为已有费用记录的图片与视频任务总数，纵轴为费用。排除存在待确认费用的人员；任务数量不代表内容质量，图形不表示因果关系。</p>
    </div>
    <div ref="canvas" v-show="rows.length" class="chart" role="img" :aria-label="`${chartTitle}，币种 ${currency}，已知费用 ${total}`" />
    <p class="hint">已知费用包含争议金额；待确认金额不按零计入。没有费用记录的日期显示为零，尚未形成费用记录的任务不在统计内。</p>
    <el-button v-if="rows.length" text @click="showData = !showData">{{ showData ? '收起统计数据' : '查看统计数据' }}</el-button>
    <el-table v-if="showData && rows.length" :data="points"><el-table-column prop="displayName" label="分组" /><el-table-column prop="totalKnownAmount" :label="`已知费用（${currency}）`" /><el-table-column prop="unknownCount" label="待确认笔数" /></el-table>
  </section>
</template>
<style scoped>
.billing-charts { border:1px solid var(--el-border-color); border-radius:12px; background:var(--el-bg-color); padding:20px; }
.chart-heading { display:flex; align-items:center; justify-content:space-between; gap:16px; }
h3 { margin:0; }
.hint { color:var(--el-text-color-secondary); line-height:1.6; font-size:13px; }
.metrics { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; margin:20px 0; }
.metrics > div { padding:16px; border-radius:8px; background:var(--el-fill-color-light); }
.metrics span { color:var(--el-text-color-secondary); font-size:13px; }
.metrics strong { display:block; margin-top:10px; font-size:22px; font-variant-numeric:tabular-nums; overflow-wrap:anywhere; }
.chart { width:100%; height:360px; }
.people-table { margin-top:16px; }
.analysis-controls { margin-top:24px; }
.analysis-controls h3 { margin-top:16px; }
.analysis-controls :deep(.el-radio-group) { display:flex; flex-wrap:wrap; gap:4px; }
.people-table small { color:var(--el-text-color-secondary); }
@media(max-width:700px) { .metrics { grid-template-columns:1fr; } .billing-charts { padding:12px; } }
</style>
