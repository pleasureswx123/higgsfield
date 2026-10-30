import type { ProjectStatus } from '@/api/projects'
export const projectStatusLabels: Record<ProjectStatus, string> = {
  active: '进行中',
  paused: '已暂停',
  archived: '已归档',
  pending_delete: '待删除',
}
export const projectRoleLabels: Record<string, string> = {
  owner: 'Owner',
  admin: '负责人',
  producer: '制作人',
  viewer: '查看者',
}
export function formatProjectDate(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Asia/Shanghai',
  }).format(new Date(value))
}
