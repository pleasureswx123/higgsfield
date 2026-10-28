<script setup lang="ts">
import DialogHeading from '@/components/shared/DialogHeading.vue'
import {
  ElDialog,
  ElForm,
  ElFormItem,
  ElInput,
  ElSelect,
  ElOption,
  ElCheckbox,
  ElPagination,
} from 'element-plus'
import Button from '@/components/ui/Button.vue'
import { useElementImport } from '@/composables/useElementImport'
const props = defineProps<{
  projectId: string
  visible?: boolean
  canImport: boolean
  canUpload: boolean
  canCreate: boolean
}>()
const emit = defineEmits<{ close: []; changed: [] }>()
const {
  active,
  form,
  confirmClose,
  discardEdit,
  batch,
  rows,
  editing,
  editUncertain,
  batchId,
  page,
  total,
  busy,
  error,
  stage,
  includeProjectName,
  fileName,
  confirmed,
  result,
  started,
  needsRefresh,
  selectFile,
  upload,
  refresh,
  edit,
  save,
  confirm,
} = useElementImport(
  props.projectId,
  () => emit('changed'),
  () => ({ canImport: props.canImport, canUpload: props.canUpload, canCreate: props.canCreate }),
  () => props.visible !== false,
)
const names = {
  uploaded: '等待解析',
  validated: '待复核',
  confirmed: '确认中',
  finished: '已完成',
  failed: '解析失败',
}
function choose(event: Event) {
  const input = event.target as HTMLInputElement
  if (input.files?.[0]) selectFile(input.files[0])
  input.value = ''
}
async function close() {
  if (await confirmClose()) emit('close')
}
</script>
<template>
  <ElDialog
    :model-value="active"
    title="导入项目元素"
    class="element-import-dialog"
    top="5vh"
    width="min(960px, 96vw)"
    append-to-body
    :before-close="close"
    :show-close="!busy && !editUncertain"
    :close-on-click-modal="false"
  >
    <template #header="{ titleId, titleClass }">
      <DialogHeading :title-id="titleId" :title-class="titleClass" title="导入项目元素" />
    </template>
    <p v-if="!canImport" class="project-error" role="alert">
      当前没有元素导入权限，不能读取或提交导入批次。
    </p>
    <template v-if="canImport && !batch">
      <p class="muted">
        支持 UTF-8 CSV 和单工作表
        XLSX。四列依次为：名称、别名、分类、描述。分类填写角色、场景、道具或其他；XLSX
        单元格须使用文本，不支持公式。解析后可修改候选，确认时才创建元素。
      </p>
      <p class="muted">
        TXT/MD 使用 UTF-8
        编码，以“角色：名称”“场景：名称”“道具：名称”或“其他：名称”开始新段落，后续正文作为描述。MD
        可使用标题标记。名称用于建议别名，重复项需复核修正。
      </p>
      <p class="muted">
        也可识别“内景：车站”“EXT. STREET -
        DAY”等场景标题，以及其后“记者：对白”或标准全大写说话人。重复出场保留为不同候选，请合并描述并排除重复项；普通叙事正文中的隐含人物和道具不会自动识别。
      </p>
      <p class="muted">
        DOCX
        沿用上述分类段落格式，读取正文及表格文字，保留段落定位；不提取图片、文本框或已删除修订文字。
      </p>
      <p class="muted">
        PDF
        须有可提取文字，沿用分类段落格式；来源显示实际页号和提取文本行号。当前不支持扫描件OCR或加密PDF，最多200页。
      </p>
      <div v-if="canUpload" class="element-import-upload">
        <input
          type="file"
          accept=".csv,.xlsx,.txt,.md,.docx,.pdf"
          aria-label="选择元素导入文件"
          :disabled="busy || started"
          @change="choose"
        />
        <span>{{ fileName }}</span>
        <ElCheckbox v-model="includeProjectName" :disabled="busy || started"
          >别名添加项目名称前缀</ElCheckbox
        >
        <Button :disabled="busy || !fileName" @click="upload">{{
          started ? '重试上传与受理' : '上传并解析'
        }}</Button>
      </div>
      <p v-else class="muted">当前没有文件上传权限，可以填写已有批次编号继续复核。</p>
      <div class="element-toolbar">
        <ElInput
          v-model="batchId"
          placeholder="已有批次编号"
          aria-label="已有批次编号"
          :disabled="busy || started"
        />
        <Button variant="ghost" :disabled="busy || !/^[1-9]\d*$/.test(batchId)" @click="refresh"
          >打开批次</Button
        >
      </div>
    </template>
    <template v-else-if="canImport && batch">
      <p v-if="needsRefresh && !busy && !editing" class="project-error" role="status">
        当前结果需要刷新，暂不能编辑或确认。若提交时响应丢失，请先刷新核对批次状态。
      </p>
      <div class="element-toolbar">
        <strong>批次 {{ batch.id }} · {{ names[batch.status] }}</strong>
        <Button variant="ghost" :disabled="busy || !!editing" @click="refresh"
          >刷新解析与复核结果</Button
        >
      </div>
      <p class="muted">
        共 {{ batch.summary.total }} 项；字段校验通过 {{ batch.summary.valid }} 项，待修正
        {{ batch.summary.invalid }} 项。请保存批次编号，之后可重新打开。
      </p>
      <p v-if="batch.status === 'uploaded'" role="status">
        文件已受理，等待后台解析。稍后点击刷新查看候选。
      </p>
      <p
        v-for="(issue, index) in batch.status === 'failed' ? batch.errors : []"
        :key="index"
        class="project-error"
      >
        {{ issue.message }}
      </p>
      <div v-if="!editing" class="element-import-rows">
        <article v-for="row in rows" :key="row.rowNo" class="element-import-row">
          <div>
            <strong>{{ row.candidate.name || '未命名' }}</strong>
            <p class="muted">
              {{ row.candidate.alias || '未填写别名' }} ·
              {{ row.isSelected ? '已选中' : '已排除' }} ·
              {{
                row.sourceLocator.paragraph
                  ? `原文第 ${row.sourceLocator.paragraph} 段`
                  : row.sourceLocator.page
                    ? `PDF第 ${row.sourceLocator.page} 页`
                    : row.sourceLocator.sheet || '原文'
              }}
              第 {{ row.sourceLocator.row || row.sourceLocator.line }} 行
            </p>
            <p v-for="(issue, index) in row.issues" :key="index" class="project-error">
              {{ issue.message }}
            </p>
            <p v-if="row.elementId">已创建元素 {{ row.elementId }}</p>
          </div>
          <Button
            v-if="batch.status === 'validated'"
            variant="ghost"
            :disabled="busy || needsRefresh"
            @click="edit(row)"
            >编辑与选择</Button
          >
        </article>
      </div>
      <ElForm
        v-else
        ref="form"
        :model="editing.candidate"
        label-position="top"
        :disabled="busy || editUncertain"
      >
        <ElCheckbox v-model="editing.isSelected">确认时创建此元素</ElCheckbox>
        <ElFormItem label="名称" prop="name" :rules="[{ max: 20000, message: '名称过长' }]">
          <ElInput v-model="editing.candidate.name" maxlength="20000" />
        </ElFormItem>
        <ElFormItem label="别名" prop="alias" :rules="[{ max: 20000, message: '别名过长' }]">
          <ElInput v-model="editing.candidate.alias" maxlength="20000" />
        </ElFormItem>
        <ElFormItem label="分类" prop="category">
          <ElSelect v-model="editing.candidate.category">
            <ElOption label="角色" value="character" /><ElOption label="场景" value="scene" />
            <ElOption label="道具" value="prop" /><ElOption label="其他" value="other" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="描述" prop="description" :rules="[{ max: 20000, message: '描述过长' }]">
          <ElInput
            v-model="editing.candidate.description"
            type="textarea"
            :rows="4"
            maxlength="20000"
          />
        </ElFormItem>
        <p class="muted">保存后重新校验；尚未修正的候选可排除。排除项不会创建元素。</p>
      </ElForm>
      <ElPagination
        v-if="total > 20"
        v-model:current-page="page"
        :page-size="20"
        :total="total"
        :disabled="busy || !!editing || needsRefresh"
        layout="prev, pager, next"
        @current-change="refresh"
      />
      <ElCheckbox
        v-if="batch.status === 'validated' && canCreate"
        v-model="confirmed"
        :disabled="busy || !!editing || needsRefresh"
      >
        已复核整个批次所有页面，确认创建全部选中候选
      </ElCheckbox>
    </template>
    <p v-if="stage" role="status">{{ stage }}</p>
    <p v-if="result" role="status">{{ result }}</p>
    <p v-if="editUncertain" role="status">
      候选保存结果尚未确认，请重试原请求；确认前保留当前内容。
    </p>
    <p v-if="error" class="project-error" role="alert">{{ error }}</p>
    <template #footer>
      <template v-if="editing && canImport">
        <Button variant="ghost" :disabled="busy || editUncertain" @click="discardEdit"
          >放弃本次编辑</Button
        >
        <Button :disabled="busy" @click="save">{{
          editUncertain ? '重试确认原请求' : '保存候选'
        }}</Button>
      </template>
      <Button v-else variant="ghost" :disabled="busy" @click="close">关闭</Button>
      <Button
        v-if="batch?.status === 'validated' && canCreate"
        :disabled="busy || !!editing || needsRefresh || !confirmed"
        @click="confirm"
        >确认整批创建</Button
      >
    </template>
  </ElDialog>
</template>
<style scoped>
.element-import-upload {
  display: grid;
  gap: 12px;
  margin: 20px 0;
}
.element-import-rows {
  max-height: 45vh;
  overflow: auto;
}
.element-import-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px;
  border-bottom: 1px solid var(--border);
}
.element-import-row > div {
  min-width: 0;
  overflow-wrap: anywhere;
}
.element-import-row p {
  margin: 6px 0;
}
</style>

<style>
.element-import-dialog {
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  margin-bottom: 5vh;
}
.element-import-dialog > .el-dialog__body {
  min-height: 0;
  overflow: auto;
}
.element-import-dialog > .el-dialog__header,
.element-import-dialog > .el-dialog__footer {
  flex-shrink: 0;
}
.element-import-dialog .el-checkbox {
  height: auto;
  min-height: 32px;
}
.element-import-dialog .el-checkbox__label {
  white-space: normal;
  overflow-wrap: anywhere;
}
</style>
