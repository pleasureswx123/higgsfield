<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter, onBeforeRouteUpdate } from 'vue-router'
import ModelSetup from '../setup/ModelSetup.vue'
import ModelHub from './ModelHub.vue'
import SupplierSetup from './SupplierSetup.vue'
import AdvancedProviders from './AdvancedProviders.vue'
const route = useRoute(), router = useRouter()
const busy = ref(false)
onBeforeRouteUpdate(() => !busy.value)
const mode = computed(() => route.query.mode === 'advanced' ? 'supplier' : (route.query.mode || 'list'))
function navigate(mode, values = {}) {
  if (busy.value) return
  router.push({ path: route.path, query: mode === 'list' ? values : { mode, ...values } })
}
</script>
<template>
  <ModelHub v-if="mode === 'list'" :start-add="route.query.add === '1'" @configure="values => navigate('model', values)" @supplier="navigate('supplier')" />
  <template v-else>
    <div class="provider-mode"><el-button :disabled="busy" @click="navigate('list')">返回模型列表</el-button></div>
    <SupplierSetup v-if="mode === 'supplier'" @busy="busy = $event" @saved="navigate('list', { add: '1' })" @advanced="navigate('connection-details')" />
    <ModelSetup v-else-if="mode === 'model'" :key="String(route.query.model || '')"
      :initial-connection="String(route.query.connection || '')" :initial-model="String(route.query.model || '')"
      @busy="busy = $event" @advanced="navigate('connection-details')" />
    <template v-else><div class="provider-mode"><p>维护详情：仅在供应商地址或连接参数发生变化时使用。日常添加模型无需操作此页。</p></div><AdvancedProviders /></template>
  </template>
</template>
<style scoped>
.provider-mode { padding: 20px 20px 0; color: var(--el-text-color-secondary); }
</style>
