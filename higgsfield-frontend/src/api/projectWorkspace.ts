import { request } from './client'
export interface TextMark {
  type: 'bold' | 'italic' | 'link'
  href?: string | null
}
export interface TextNode {
  type: 'text'
  text: string
  marks: TextMark[]
}
export interface Paragraph {
  type: 'paragraph'
  content: TextNode[]
}
export interface BriefBody {
  schemaVersion: 1
  type: 'doc'
  content: Paragraph[]
}
export interface Brief {
  projectId: string
  body: BriefBody
  revision: string
  updateTime: string
  allowedActions: string[]
}
export interface Member {
  userId: string
  displayName: string
  roleId: string
  status: 'active' | 'removed'
  revision: string
  joinedAt: string
}
export interface ProjectRole {
  id: string
  code: string
  name: string
  permissions: string[]
  canGrant: boolean
}
export interface Candidate {
  userId: string
  displayName: string
}
interface Result<T> {
  code: number
  data: T
}
const root = (id: string) => `/api/v1/projects/${encodeURIComponent(id)}`
export const readBrief = (id: string, signal?: AbortSignal) =>
  request<Result<Brief>>({ url: `${root(id)}/brief`, signal })
export const saveBrief = (id: string, data: { revision: string; body: BriefBody }, key: string, signal?: AbortSignal) =>
  request<Result<Brief>>({
    url: `${root(id)}/brief`,
    method: 'PUT',
    data,
    headers: { 'Idempotency-Key': key },
    signal,
  })
export const readMembers = (id: string, pageNum: number, status: string, signal?: AbortSignal) =>
  request<{ code: number; rows: Member[]; total: number }>({
    url: `${root(id)}/members`,
    params: { pageNum, pageSize: 20, status },
    signal,
  })
export const readRoles = (id: string, signal?: AbortSignal) =>
  request<Result<{ items: ProjectRole[] }>>({ url: `${root(id)}/roles`, signal })
export const findCandidate = (id: string, account: string) =>
  request<Result<{ items: Candidate[] }>>({
    url: `${root(id)}/member-candidates`,
    params: { account },
  })
export const addMember = (id: string, data: { userId: string; roleId: string }, key: string) =>
  request<Result<Member>>({
    url: `${root(id)}/members`,
    method: 'POST',
    data,
    headers: { 'Idempotency-Key': key },
  })
export const changeMember = (id: string, member: Member, roleId: string, key: string) =>
  request<Result<Member>>({
    url: `${root(id)}/members/${member.userId}`,
    method: 'PATCH',
    data: { revision: member.revision, roleId },
    headers: { 'Idempotency-Key': key },
  })
export const removeMember = (id: string, member: Member, key: string) =>
  request<Result<Member>>({
    url: `${root(id)}/members/${member.userId}`,
    method: 'DELETE',
    params: { revision: member.revision },
    headers: { 'Idempotency-Key': key },
  })
