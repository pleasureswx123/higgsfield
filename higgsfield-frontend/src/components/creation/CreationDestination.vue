<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { ElForm, ElFormItem, ElInput, type FormInstance } from 'element-plus'
import { IconFolder, IconChevronRight } from '@tabler/icons-vue'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import Button from '@/components/ui/Button.vue'
import { useCreationDestination } from '@/composables/useCreationDestination'
const props = defineProps<{ projectId: string; disabled?: boolean; canCreate?: boolean }>()
const emit = defineEmits<{ created: []; generationBlock: [reason: string] }>()
const formRef = ref<FormInstance>()
const fields = reactive({ name: '' })
const editing = ref(false)
const folder = defineModel<string | null>({ required: true })
const destination = useCreationDestination(props.projectId, () => folder.value, () => !!props.canCreate)
watch(destination.generationBlock, reason => emit('generationBlock', reason), { immediate: true, flush: 'sync' })
const busy = computed(() => !!props.disabled || destination.creating.value)
function beginCreate() {
  if (busy.value || !props.canCreate) return
  editing.value = true; destination.open.value = true
}
async function save() {
  if (busy.value || !props.canCreate || !await formRef.value?.validate().catch(() => false)) return
  const item = await destination.create(fields.name)
  if (!item) return
  folder.value = item.id; destination.open.value = false; editing.value = false; fields.name = ''; emit('created')
}
function select() {
  if (props.disabled || destination.loading.value || destination.error.value) return
  folder.value = destination.path.value.at(-1)?.id ?? null
  destination.open.value = false
}
</script>
<template>
  <div v-if="destination.emptyProject.value && !folder" class="destination-guide">
    <div><strong>为第一次创作准备一个文件夹</strong><p>图片和视频集中保存，后续更容易查找。</p></div>
    <Button v-if="canCreate" :disabled="busy" @click="destination.path.value = []; beginCreate()">创建文件夹</Button>
    <span v-else>可请项目负责人创建文件夹</span>
  </div>
  <div v-else class="creation-destination"><IconFolder :size="16" /><span>保存至</span><button type="button" :disabled="disabled" @click="editing = destination.uncertain.value; destination.start()">{{ destination.label.value }}<IconChevronRight :size="14" /></button></div>
  <Dialog :open="destination.open.value" @update:open="value => { if (!destination.creating.value) destination.open.value = value }">
    <DialogContent class="studio-dialog">
      <DialogHeader><DialogTitle>选择产出保存位置</DialogTitle><DialogDescription>后续生成的图片和视频将保存到所选位置，已有素材不会移动。</DialogDescription></DialogHeader>
      <ElForm v-if="editing" ref="formRef" :model="fields" label-position="top" @submit.prevent>
        <ElFormItem label="文件夹名称" prop="name" :rules="[{ required: true, whitespace: true, message: '请输入文件夹名称', trigger: 'blur' }, { max: 200, message: '名称不能超过 200 个字符', trigger: 'blur' }]">
          <ElInput v-model="fields.name" placeholder="例如：第一个镜头" :maxlength="200" :disabled="busy || destination.uncertain.value" @keyup.enter="save" />
        </ElFormItem>
        <p v-if="destination.createError.value" role="alert">{{ destination.createError.value }}</p>
        <p v-if="destination.uncertain.value && !destination.creating.value">创建结果尚未确认，请重试确认；不会重复创建。</p>
      </ElForm>
      <template v-else>
      <nav class="destination-path" aria-label="保存位置路径">
        <button @click="destination.navigate([])">全部素材</button>
        <template v-for="(item, index) in destination.path.value" :key="item.id"><span>/</span><button @click="destination.navigate(destination.path.value.slice(0, index + 1))">{{ item.name }}</button></template>
      </nav>
      <p v-if="destination.loading.value" role="status">正在读取文件夹…</p>
      <p v-else-if="destination.error.value" role="alert">{{ destination.error.value }} <button @click="destination.load()">重试</button></p>
      <div v-else class="destination-folders">
        <button v-for="item in destination.rows.value" :key="item.id" @click="destination.navigate([...destination.path.value, item])"><IconFolder :size="18" /><span>{{ item.name }}</span><IconChevronRight :size="16" /></button>
        <p v-if="!destination.rows.value.length">当前目录没有子文件夹，可直接保存到这里。</p>
      </div>
      <div class="destination-pages"><Button variant="ghost" :disabled="destination.page.value === 1 || destination.loading.value" @click="destination.page.value--; destination.load()">上一页</Button><Button variant="ghost" :disabled="!destination.hasNext.value || destination.loading.value" @click="destination.page.value++; destination.load()">下一页</Button></div>
      <Button v-if="canCreate" variant="outline" :disabled="busy || destination.loading.value || !!destination.error.value" @click="beginCreate">新建文件夹</Button>
      </template>
      <DialogFooter v-if="editing"><Button variant="outline" :disabled="destination.creating.value" @click="destination.open.value = false">取消</Button><Button :disabled="busy" @click="save">{{ destination.creating.value ? '正在创建…' : destination.uncertain.value ? '重试确认' : '创建并选中' }}</Button></DialogFooter>
      <DialogFooter v-else><Button variant="outline" @click="destination.open.value = false">取消</Button><Button :disabled="disabled || destination.loading.value || !!destination.error.value" @click="select">保存到这里</Button></DialogFooter>
    </DialogContent>
  </Dialog>
</template>
<style scoped>
.destination-guide { display:flex; align-items:center; gap:12px; flex-wrap:wrap; padding:14px 16px; border:1px solid var(--border); border-radius:12px; background:var(--surface-raised); color:var(--foreground); font-size:13px; }
.destination-guide p { margin:4px 0 0; color:var(--muted-foreground); }
.creation-destination,.creation-destination button,.destination-path { display:flex; align-items:center; gap:7px; }
.creation-destination { font-size:12px; color:var(--muted-foreground); flex-wrap:wrap; }
.creation-destination button,.destination-path button { border:0; background:transparent; color:var(--foreground); cursor:pointer; font:inherit; }
.creation-destination button { max-width:100%; text-align:left; }
.destination-path { flex-wrap:wrap; font-size:13px; }
.destination-folders { max-height:280px; overflow:auto; }
.destination-folders > button { display:flex; width:100%; align-items:center; gap:10px; padding:12px; color:var(--foreground); background:var(--surface-raised); border:0; border-radius:8px; margin-bottom:4px; cursor:pointer; }
.destination-folders > button span { flex:1; text-align:left; }
.destination-folders > button:hover { background:var(--surface-hover); }
.destination-pages { display:flex; justify-content:space-between; }
button:focus-visible { outline:2px solid var(--ring); outline-offset:2px; }
</style>
