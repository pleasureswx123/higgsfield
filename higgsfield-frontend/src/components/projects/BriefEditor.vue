<script setup lang="ts">
import { ref, watch } from 'vue'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import { ElInput } from 'element-plus'
import { IconBold, IconItalic, IconLink, IconArrowBackUp, IconArrowForwardUp } from '@tabler/icons-vue'
import type { BriefBody } from '@/api/projectWorkspace'
import { toBriefEditor, fromBriefEditor, briefOutline, hasBriefText } from '@/utils/briefDocument'
import Button from '@/components/ui/Button.vue'
const model = defineModel<BriefBody>({ required: true })
const props = defineProps<{ disabled: boolean }>()
const linkOpen = ref(false), href = ref(''), linkError = ref('')
const editor = useEditor({
  extensions: [StarterKit.configure({ heading: false, blockquote: false, bulletList: false,
    orderedList: false, listItem: false, listKeymap: false, code: false, codeBlock: false,
    horizontalRule: false, strike: false, underline: false, trailingNode: false,
    link: { openOnClick: false, autolink: false, linkOnPaste: false },
  })],
  content: toBriefEditor(model.value), editable: !props.disabled,
  editorProps: { attributes: { role: 'textbox', 'aria-label': '项目说明正文', 'aria-multiline': 'true' } },
  onUpdate: ({ editor }) => { model.value = fromBriefEditor(editor.getJSON()) },
})
watch(() => props.disabled, value => editor.value?.setEditable(!value, false))
watch(model, value => {
  if (editor.value && JSON.stringify(fromBriefEditor(editor.value.getJSON())) !== JSON.stringify(value))
    editor.value.commands.setContent(toBriefEditor(value), { emitUpdate: false })
}, { deep: true })
function openLink() {
  href.value = editor.value?.getAttributes('link').href || ''
  linkError.value = ''; linkOpen.value = !linkOpen.value
}
function applyLink() {
  if (props.disabled) return
  const value = href.value.trim()
  if (value) {
    try {
      const url = new URL(value)
      if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || /[\s\x00-\x1f]/.test(value)) throw new Error()
    } catch { linkError.value = '请输入有效的 http 或 https 链接，不包含账号或密码。'; return }
    editor.value?.chain().focus().extendMarkRange('link').setLink({ href: value }).run()
  } else editor.value?.chain().focus().extendMarkRange('link').unsetLink().run()
  linkOpen.value = false
}
function outline() {
  if (props.disabled || hasBriefText(model.value)) return
  model.value = briefOutline()
}
</script>
<template>
  <div class="description-editor">
    <div class="description-toolbar" role="toolbar" aria-label="正文格式">
      <Button variant="ghost" aria-label="加粗" :aria-pressed="editor?.isActive('bold')" :disabled="disabled" @click="editor?.chain().focus().toggleBold().run()"><IconBold :size="18" /></Button>
      <Button variant="ghost" aria-label="斜体" :aria-pressed="editor?.isActive('italic')" :disabled="disabled" @click="editor?.chain().focus().toggleItalic().run()"><IconItalic :size="18" /></Button>
      <Button variant="ghost" aria-label="设置链接" :disabled="disabled" @click="openLink"><IconLink :size="18" /></Button>
      <Button variant="ghost" aria-label="撤销" :disabled="disabled || !editor?.can().undo()" @click="editor?.chain().focus().undo().run()"><IconArrowBackUp :size="18" /></Button>
      <Button variant="ghost" aria-label="重做" :disabled="disabled || !editor?.can().redo()" @click="editor?.chain().focus().redo().run()"><IconArrowForwardUp :size="18" /></Button>
      <Button v-if="!hasBriefText(model)" variant="ghost" :disabled="disabled" class="description-outline" @click="outline">插入填写提纲</Button>
    </div>
    <div v-if="linkOpen" class="description-link">
      <ElInput v-model="href" aria-label="链接地址" placeholder="https://…（清空可移除链接）" :disabled="disabled" @keydown.enter.prevent="applyLink" />
      <Button variant="outline" :disabled="disabled" @click="applyLink">应用</Button>
      <Button variant="ghost" @click="linkOpen = false">取消</Button>
      <p v-if="linkError" role="alert" class="project-error">{{ linkError }}</p>
    </div>
    <p class="description-writing-hint">可以写制作目标、视觉风格、交付要求和注意事项；按回车继续写下一段。</p>
    <EditorContent :editor="editor" />
  </div>
</template>
<style scoped>
.description-editor { border:1px solid var(--border); border-radius:12px; background:var(--surface); overflow:hidden; }
.description-toolbar { display:flex; flex-wrap:wrap; gap:4px; padding:8px; border-bottom:1px solid var(--border); }
.description-toolbar button { min-height:32px; padding:6px 9px; }
.description-toolbar button[aria-pressed='true'] { background:var(--surface-hover); }
.description-outline { margin-left:auto; }
.description-writing-hint { color:var(--muted-foreground); font-size:12px; padding:12px 20px 0; margin:0; }
.description-editor :deep(.tiptap) { min-height:280px; padding:16px 20px 24px; outline:none; line-height:1.85; overflow-wrap:anywhere; white-space:pre-wrap; }
.description-editor :deep(.tiptap:focus) { box-shadow:inset 0 0 0 2px var(--ring); }
.description-editor :deep(.tiptap p) { margin:0 0 16px; }
.description-editor :deep(.tiptap a) { text-decoration:underline; text-underline-offset:3px; }
.description-link { display:flex; flex-wrap:wrap; gap:8px; padding:12px; border-bottom:1px solid var(--border); }
.description-link .el-input { flex:1; min-width:180px; }
.description-link p { width:100%; margin:0; }
</style>
