import { computed, onBeforeUnmount, onDeactivated, ref, shallowRef, watch } from 'vue'
import { Editor, Extension, type Range } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Mention from '@tiptap/extension-mention'
import { exitSuggestion, type SuggestionProps } from '@tiptap/suggestion'
import { Plugin, type Transaction } from '@tiptap/pm/state'
import { closeHistory, isHistoryTransaction } from '@tiptap/pm/history'
import type { DraftReference, ModelCapability } from '@/api/creation'
import { searchReferences, type ReferenceCandidate } from '@/api/references'
import type { PromptDocument } from '@/utils/promptDocument'
import {
  fromEditorDocument,
  referenceNumberLabels,
  toEditorDocument,
  reconcilePromptReferences,
  insertPromptText,
  bindNumberedMediaReferences,
} from '@/utils/promptEditorDocument'
import { prepareMentionReference, prepareMentionBatch } from '@/utils/promptMention'
import { compatibleReferenceRoles, selectReferenceMedia } from '@/utils/draftReferences'
import { useReferencePicker } from './useReferencePicker'

interface EditorState {
  document: PromptDocument
  references: DraftReference[]
  projectId: string
  model?: ModelCapability | null
  disabled?: boolean
  context: string
}

/** Tiptap 管理编辑、标签、选区和撤销；这里只连接项目候选与草稿契约。 */
export function usePromptEditor(
  state: () => EditorState,
  apply: (value: { prompt: PromptDocument; references: DraftReference[] }) => void,
) {
  const editor = shallowRef<Editor>()
  const error = ref(''),
    visible = ref(false),
    highlighted = ref(0)
  const anchor = shallowRef<{ getBoundingClientRect: () => DOMRect }>()
  const picker = useReferencePicker(
    () => state().projectId,
    () => !!state().disabled,
  )
  const localCandidates = computed<ReferenceCandidate[]>(() => {
    const labels = referenceNumberLabels(state().references)
    const unique = state().references.filter(
      (item, index, all) =>
        !item.elementRevisionId &&
        all.findIndex((value) => value.referenceKey === item.referenceKey) === index,
    )
    return unique.map((item) => {
      const label = labels.get(item.referenceKey)!
      return {
        kind: 'asset' as const,
        id: item.referenceKey,
        projectId: state().projectId,
        displayName: label,
        alias: label.toLowerCase().replace(' ', '-'),
        assetVersionIds: [item.assetVersionId],
        allowedMediaRoles: [item.mediaRole],
      }
    })
  })
  const mentionedKeys = computed(() => new Set(state().document.content.flatMap(
    paragraph => paragraph.content.flatMap(node => node.type === 'mention' ? [node.referenceKey] : []),
  )))
  const rows = computed(() =>
    [
      ...localCandidates.value.filter((item) =>
        `${item.displayName} ${item.alias}`.toLowerCase().includes(picker.q.value.toLowerCase()),
      ),
      ...picker.rows.value,
    ].map((candidate) => ({
      candidate,
      selected: state().references.some((item) =>
        mentionedKeys.value.has(item.referenceKey) && (candidate.kind === 'asset'
          ? item.referenceKey === candidate.id
          : item.elementRevisionId === candidate.elementRevisionId),
      ),
      disabled:
        !candidate.assetVersionIds.length ||
        !compatibleReferenceRoles(candidate, state().model).length,
    })),
  )
  let range: Range | undefined,
    applying = false,
    signature = '',
    pendingReferences: DraftReference[] | undefined
  const historyReferences = new Map<string, DraftReference[]>()
  function referencesFor(transaction: Transaction) {
    const before = transaction.before.toJSON(),
      after = transaction.doc.toJSON()
    const remembered = isHistoryTransaction(transaction)
      ? (historyReferences.get(JSON.stringify(after)) ?? [])
      : []
    const base = pendingReferences ?? state().references
    // 历史中的同一个键可能属于当时的另一份素材，以该历史文档的绑定为准。
    const keys = new Set(remembered.map((item) => item.referenceKey))
    return reconcilePromptReferences(
      before,
      after,
      base.filter((item) => !keys.has(item.referenceKey)).concat(remembered),
    )
  }
  function close() {
    visible.value = false
    range = undefined
    picker.close()
  }
  function dismiss() {
    if (editor.value) exitSuggestion(editor.value.view)
    close()
  }
  function suggest(props: SuggestionProps) {
    range = props.range
    const rect = props.clientRect?.()
    if (rect) anchor.value = { getBoundingClientRect: () => rect }
    visible.value = true
    if (!picker.open.value || picker.q.value !== props.query) {
      highlighted.value = 0
      picker.q.value = props.query
      picker.show('element')
    }
  }
  function insert(
    candidate: ReferenceCandidate,
    role?: string,
    target = range ?? editor.value?.state.selection,
  ) {
    const current = editor.value
    if (!current || state().disabled || !target) return false
    try {
      if (candidate.projectId !== state().projectId) throw new Error('请先将元素复制到当前项目')
      const result =
        candidate.kind === 'asset'
          ? { references: state().references, key: candidate.id }
          : prepareMentionReference(state().references, candidate, state().model, role)
      if (!result.references.some((item) => item.referenceKey === result.key))
        throw new Error('此素材已被移除')
      const transaction = closeHistory(current.state.tr).replaceWith(target.from, target.to, [
        current.schema.nodes.mention!.create({ id: result.key, label: candidate.displayName }),
        current.schema.text(' '),
      ])
      result.references = reconcilePromptReferences(
        transaction.before.toJSON(),
        transaction.doc.toJSON(),
        result.references,
      )
      const prompt = fromEditorDocument(transaction.doc.toJSON(), result.references)
      signature = JSON.stringify(prompt)
      pendingReferences = result.references
      applying = true
      current.view.dispatch(transaction)
      current.view.dispatch(closeHistory(current.state.tr))
      apply({ prompt, references: result.references })
      error.value = ''
      dismiss()
      current.commands.focus()
      return true
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : '引用元素失败'
      return false
    } finally {
      applying = false
      pendingReferences = undefined
    }
  }
  function select(index: number) {
    const row = rows.value[index]
    if (row && !row.disabled && (row.candidate.kind === 'asset' || picker.canSelect(row.candidate)))
      insert(selectReferenceMedia(row.candidate))
  }
  let pasteController: AbortController | undefined
  async function resolvePastedMentions(text: string, start: number, current: Editor, pasteTime: number) {
    pasteController?.abort()
    const controller = new AbortController()
    pasteController = controller
    const snapshot = JSON.stringify(current.getJSON())
    const projectId = state().projectId
    const matches = [...text.matchAll(/@((?:Image|Video) \d+|[^\s@，。；！？]+)/giu)]
    const candidates = new Map<string, ReferenceCandidate>()
    try {
      for (const name of new Set(matches.map((match) => match[1]!))) {
        const local = localCandidates.value.find((item) =>
          [item.displayName, item.alias].some(
            (value) => value?.toLowerCase() === name.toLowerCase(),
          ),
        )
        if (local) {
          candidates.set(name, local)
          continue
        }
        const result = await searchReferences(
          { projectId, q: name, kind: 'element', pageNum: 1, pageSize: 100 },
          controller.signal,
        )
        const exact = result.rows.filter((item) => item.displayName === name || item.alias === name)
        if (exact.length === 1 && exact[0]!.assetVersionIds.length)
          candidates.set(name, selectReferenceMedia(exact[0]!))
      }
      if (
        controller.signal.aborted ||
        editor.value !== current ||
        state().disabled ||
        state().projectId !== projectId ||
        JSON.stringify(current.getJSON()) !== snapshot
      )
        return
      // 先累计所有引用，再用一个事务提交；Vue props 在同一轮同步循环中尚未更新。
      const resolved = matches.flatMap((match) => {
        const candidate = candidates.get(match[1]!)
        return candidate ? [{ match, candidate }] : []
      })
      if (!resolved.length) return
      const batch = prepareMentionBatch(
        state().references,
        resolved.map((item) => item.candidate),
        state().model,
      )
      // 自动识别属于本次粘贴，沿用时间使历史插件合并为一次操作。
      const transaction = current.state.tr.setTime(pasteTime)
      for (let index = resolved.length - 1; index >= 0; index--) {
        const { match, candidate } = resolved[index]!
        transaction.replaceWith(
          start + match.index!,
          start + match.index! + match[0].length,
          current.schema.nodes.mention!.create({
            id: batch.keys[index],
            label: candidate.displayName,
          }),
        )
      }
      batch.references = reconcilePromptReferences(
        transaction.before.toJSON(),
        transaction.doc.toJSON(),
        batch.references,
      )
      const prompt = fromEditorDocument(transaction.doc.toJSON(), batch.references)
      signature = JSON.stringify(prompt)
      pendingReferences = batch.references
      applying = true
      try {
        current.view.dispatch(transaction)
        current.view.dispatch(closeHistory(current.state.tr))
        apply({ prompt, references: batch.references })
        error.value = ''
        dismiss()
      } finally {
        applying = false
        pendingReferences = undefined
      }
    } catch (cause) {
      if (!controller.signal.aborted)
        error.value = cause instanceof Error ? cause.message : '自动引用失败，请用 @ 重新选择'
    }
  }
  function create() {
    pasteController?.abort()
    error.value = ''
    close()
    editor.value?.destroy()
    signature = JSON.stringify(state().document)
    historyReferences.clear()
    editor.value = new Editor({
      content: toEditorDocument(state().document),
      editable: !state().disabled,
      extensions: [
        StarterKit.configure({
          heading: false,
          blockquote: false,
          bulletList: false,
          orderedList: false,
          listItem: false,
          listKeymap: false,
          codeBlock: false,
          code: false,
          horizontalRule: false,
          strike: false,
          underline: false,
          link: { openOnClick: false },
          trailingNode: false,
        }),
        Mention.configure({
          HTMLAttributes: { class: 'prompt-element-tag' },
          deleteTriggerWithBackspace: true,
          renderText: ({ node }) => `@${node.attrs.label || '已引用元素'}`,
          suggestion: {
            char: '@',
            allowedPrefixes: null,
            items: () => [],
            render: () => ({
              onStart: suggest,
              onUpdate: suggest,
              onExit: close,
              onKeyDown: ({ event }) => {
                if (event.isComposing) return false
                if (event.key === 'Escape') {
                  dismiss()
                  return true
                }
                if (event.key === 'Enter' && visible.value) {
                  select(highlighted.value)
                  return true
                }
                if (['ArrowDown', 'ArrowUp'].includes(event.key) && visible.value) {
                  const available = rows.value.flatMap((row, index) =>
                    row.disabled ? [] : [index],
                  )
                  const index = available.indexOf(highlighted.value)
                  highlighted.value =
                    available[
                      (index + (event.key === 'ArrowDown' ? 1 : -1) + available.length) %
                        available.length
                    ] ?? 0
                  return true
                }
                return false
              },
            }),
          },
        }),
        Extension.create({
          name: 'promptLimits',
          addProseMirrorPlugins: () => [
            new Plugin({
              filterTransaction(transaction) {
                if (!transaction.docChanged) return true
                try {
                  const nextReferences = referencesFor(transaction)
                  const keys = new Set(nextReferences.map((item) => item.referenceKey))
                  transaction.doc.descendants((node) => {
                    if (node.type.name === 'mention' && !keys.has(String(node.attrs.id)))
                      throw new Error('引用素材已移除，请重新选择元素')
                  })
                  fromEditorDocument(transaction.doc.toJSON(), nextReferences)
                  historyReferences.set(
                    JSON.stringify(transaction.before.toJSON()),
                    state().references.map((item) => ({ ...item })),
                  )
                  historyReferences.set(JSON.stringify(transaction.doc.toJSON()), nextReferences)
                  if (historyReferences.size > 220)
                    historyReferences.delete(historyReferences.keys().next().value!)
                  return true
                } catch (cause) {
                  error.value = cause instanceof Error ? cause.message : '提示词超出限制'
                  return false
                }
              },
            }),
          ],
        }),
      ],
      editorProps: {
        attributes: {
          role: 'textbox',
          'aria-label': '创作描述',
          'aria-multiline': 'true',
          'data-placeholder': '描述你想创作的画面，输入 @ 引用元素…',
        },
        // 跨页面粘贴只保留文字，避免把别的草稿的引用键误认成本项目引用。
        handlePaste(view, event) {
          const text = event.clipboardData?.getData('text/plain')
          if (text === undefined) return false
          event.preventDefault()
          const { transaction, start } = insertPromptText(closeHistory(view.state.tr), text)
          view.dispatch(transaction)
          if (editor.value && text.includes('@'))
            void resolvePastedMentions(text, start, editor.value, transaction.time)
          return true
        },
      },
      onUpdate({ editor: current, transaction }) {
        if (applying || !transaction.docChanged) return
        const nextReferences = referencesFor(transaction)
        const prompt = fromEditorDocument(current.getJSON(), nextReferences)
        signature = JSON.stringify(prompt)
        apply({ prompt, references: nextReferences })
        error.value = ''
      },
      onBlur: () => {
        visible.value = false
      },
    })
  }
  watch([() => state().projectId, () => state().context], create, { immediate: true })
  watch(
    [editor, () => JSON.stringify(state().references), () => state().disabled],
    () => {
      const current = editor.value
      if (!current || applying || state().disabled) return
      // 添加素材或恢复草稿后补齐编号引用，不重建编辑器，保留正文、选区和撤销历史。
      const transaction = bindNumberedMediaReferences(closeHistory(current.state.tr), state().references)
      if (transaction.docChanged) {
        current.view.dispatch(transaction)
        current.view.dispatch(closeHistory(current.state.tr))
      }
    },
    { immediate: true, flush: 'post' },
  )
  watch(
    () => state().document,
    (document) => {
      if (!applying && JSON.stringify(document) !== signature) create()
    },
    { deep: true },
  )
  watch(
    () => state().disabled,
    (disabled) => {
      editor.value?.setEditable(!disabled, false)
      if (disabled) {
        pasteController?.abort()
        dismiss()
      }
    },
  )
  watch(() => state().model?.versionId, dismiss)
  watch(picker.contextRevision, () => {
    pasteController?.abort()
    dismiss()
  })
  onDeactivated(() => {
    pasteController?.abort()
    dismiss()
  })
  onBeforeUnmount(() => {
    pasteController?.abort()
    editor.value?.destroy()
  })
  return { editor, rows, picker, error, visible, anchor, highlighted, select, insert }
}
