import { request } from './client'

export type Scalar = string | number | boolean
export interface DraftReference {
  referenceKey: string
  assetVersionId: string
  elementRevisionId: string | null
  mediaRole: string
  ordinal: number
}
export interface DraftSummary {
  id: string
  projectId: string
  kind: 'image' | 'video'
  revision: string
  updateTime: string
  promptExcerpt: string
  modelVersionId: string | null
}
export type PromptNode =
  | {
      type: 'text'
      text: string
      marks?: { type: 'bold' | 'italic' | 'link'; href?: string | null }[]
    }
  | { type: 'mention'; referenceKey: string }
export interface ParameterRule {
  type: 'string' | 'integer' | 'number' | 'boolean'
  enum?: Scalar[] | null
  minimum?: number | null
  maximum?: number | null
  minLength?: number | null
  maxLength?: number | null
}
export interface ModelCapability {
  id: string
  versionId: string
  displayName: string
  kind: 'image' | 'video'
  menuMeta: {
    aliases: string[]
    family: string
    releaseLabel: string
    market: string
    tier: string
  }
  parametersSchema: { properties: Record<string, ParameterRule>; required: string[] }
  defaultParameters: Record<string, Scalar>
  referenceRules: {
    roles: Record<string, { mediaTypes: string[]; minCount: number; maxCount: number }>
    maxTotal: number
  }
  availability: { available: boolean; reasonCode?: string }
}
export interface DraftBody {
  schemaVersion: 1
  prompt: {
    schemaVersion: 1
    type: 'doc'
    content: { type: 'paragraph'; content: PromptNode[] }[]
  }
  modelVersionId: string | null
  parameters: Record<string, Scalar>
  folderId?: string | null
  sourceJobId?: string | null
  targetElementId?: string | null
  returnContext?: { route: 'project-elements'; projectId: string; elementId: string } | null
}
export interface CreationDraft {
  id: string
  projectId: string
  kind: 'image' | 'video'
  body: DraftBody
  revision: string
  updateTime: string
  references: DraftReference[]
}
export const getCreationDrafts = (
  params: { projectId: string; kind?: 'image' | 'video'; pageNum: number; pageSize: number },
  signal?: AbortSignal,
) =>
  request<{ code: number; rows: DraftSummary[]; total: number; hasNext: boolean }>({
    url: '/api/v1/drafts',
    params,
    signal,
  })
export const getCreationDraft = (id: string, signal?: AbortSignal) =>
  request<{ code: number; data: CreationDraft }>({
    url: `/api/v1/drafts/${encodeURIComponent(id)}`,
    signal,
  })
export const getModelCatalog = (
  params: {
    projectId: string
    kind: 'image' | 'video'
    versionId?: string
    q?: string
    pageNum: number
    pageSize: number
  },
  signal?: AbortSignal,
) =>
  request<{ code: number; rows: ModelCapability[]; total: number }>({
    url: '/api/v1/model-profiles',
    params,
    signal,
  })
export const saveCreationDraft = (
  draft: CreationDraft | null,
  projectId: string,
  kind: 'image' | 'video',
  body: DraftBody,
  key: string,
  references: DraftReference[] = [],
) =>
  request<{ code: number; data: CreationDraft }>({
    url: draft ? `/api/v1/drafts/${draft.id}` : '/api/v1/drafts',
    method: draft ? 'PUT' : 'POST',
    headers: { 'Idempotency-Key': key },
    data: { ...(draft ? { revision: draft.revision } : { projectId, kind }), body, references },
  })
