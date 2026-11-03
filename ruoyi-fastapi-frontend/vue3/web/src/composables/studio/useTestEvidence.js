import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { getCredentialTestDetails, getCredentialTestRuntime, getCredentialTestVideo, getCredentialTestPreview } from '@/api/studio/credentials'

/** 自动刷新仅访问平台证据，不发送供应商生成请求。 */
export function useTestEvidence(props, emit) {
  const runtime = ref(), detail = ref(), preview = ref(), loading = ref(false), error = ref(''), copied = ref(false), videoUrl = ref('')
  let alive = true, epoch = 0, timer, busy = false
  function clearVideo() { if (videoUrl.value) URL.revokeObjectURL(videoUrl.value); videoUrl.value = '' }
  async function health() {
    try { const result = await getCredentialTestRuntime(); if (alive) { runtime.value = result.data; emit('ready', result.data.ready) } }
    catch { if (alive) { runtime.value = { ready: false, message: '暂时无法读取服务状态，请稍后刷新。' }; emit('ready', false) } }
  }
  async function refresh() {
    if (busy || !alive) return
    const ticket = epoch
    if (!props.testId && (!props.credentialVersionId || !props.modelVersionId || !props.costCenterId)) return
    busy = true; loading.value = true; error.value = ''
    try {
      const result = props.testId ? await getCredentialTestDetails(props.testId) : await getCredentialTestPreview(
        props.credentialVersionId, { modelVersionId: props.modelVersionId, costCenterId: props.costCenterId })
      if (alive && ticket === epoch) { if (props.testId) detail.value = result.data; else preview.value = result.data }
    } catch (cause) { if (alive && ticket === epoch) error.value = cause?.message || '读取详情失败，请刷新；不会重新生成。' }
    finally { busy = false; if (alive && ticket === epoch) loading.value = false; else if (alive) refresh() }
  }
  async function loadVideo() {
    const ticket = epoch
    try { const blob = await getCredentialTestVideo(props.testId); if (alive && ticket === epoch) { clearVideo(); videoUrl.value = URL.createObjectURL(blob) } }
    catch { if (alive && ticket === epoch) error.value = '读取测试视频失败，请重试；不会再次生成。' }
  }
  async function copy(curl) {
    try { await navigator.clipboard.writeText(curl); copied.value = true }
    catch { error.value = '复制未成功，可选中 cURL 文本手动复制。' }
  }
  watch(() => [props.testId, props.credentialVersionId, props.modelVersionId, props.costCenterId], () => {
    epoch++; clearVideo(); detail.value = preview.value = undefined; copied.value = false; error.value = ''; refresh()
  }, { immediate: true })
  onMounted(() => { health(); timer = setInterval(() => { health(); if (props.testId && (!detail.value || detail.value.testState === '0')) refresh() }, 5000) })
  onBeforeUnmount(() => { alive = false; epoch++; clearInterval(timer); clearVideo() })
  return { runtime, detail, preview, loading, error, copied, videoUrl, health, refresh, copy, loadVideo }
}
