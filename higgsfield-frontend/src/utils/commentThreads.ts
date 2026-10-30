import type { MediaComment } from '@/api/comments'
/** 保留讨论上下文；搜索命中回复时也展示所属讨论。 */
export function groupCommentThreads(rows: MediaComment[], search = '', sortByVideoTime = false) {
  const groups = new Map<string, MediaComment[]>()
  for (const row of rows) {
    if (row.deleted) continue
    const group = groups.get(row.threadId) || []
    group.push(row)
    groups.set(row.threadId, group)
  }
  const result = [...groups].map(([id, comments]) => ({ id, comments: comments.sort((a, b) => Date.parse(a.createTime) - Date.parse(b.createTime)) }))
    .filter(group => !search || group.comments.some(row => row.body?.includes(search)))
  if (sortByVideoTime) {
    // 仅排序讨论组，不打散回复；未绑定视频时间的讨论排在最后。
    const timestamp = (comments: MediaComment[]) => {
      const root = comments.find(row => !row.parentId)
      const time = root?.videoTime
      return time != null && time !== '' && Number.isFinite(Number(time)) ? Number(time) : Infinity
    }
    result.sort((a, b) => {
      const first = timestamp(a.comments), second = timestamp(b.comments)
      if (first !== second) return first < second ? -1 : 1
      return Date.parse(a.comments[0]!.createTime) - Date.parse(b.comments[0]!.createTime)
    })
  }
  return result
}
