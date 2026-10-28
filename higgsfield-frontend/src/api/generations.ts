import { request, requestBlob, requestEventStream } from './client'
import { parseEventStream, type ServerEvent } from '@/utils/eventStream'
import type { DraftBody, DraftReference } from './creation'

export const retryGenerationArchive = (
  id: string,
  data: { revision: string; outputIds: string[] },
  key: string,
  signal?: AbortSignal,
) =>
  request<{
    code: number
    data: { jobId: string; revision: string; accepted: boolean; outputIds: string[] }
  }>({
    url: `/api/v1/generations/${encodeURIComponent(id)}/retry-archive`,
      signal,
    method: 'post',
    data,
    headers: { 'Idempotency-Key': key },
  })

export interface GenerationSubmission {
  projectId: string
  kind: 'image' | 'video'
  modelVersionId: string
  prompt: DraftBody['prompt']
  parameters: DraftBody['parameters']
  references: DraftReference[]
  folderId?: string | null
  sourceJobId?: string | null
  draftId?: string
  draftRevision?: string
  targetElementId?: string
  estimateToken?: string
}
export interface GenerationValidation {
  valid: boolean
  issues: { field: string; code: string; message: string }[]
  normalizedParameters: Record<string, unknown>
  estimateVisibility: 'visible' | 'hidden'
  estimate?: { amount: string; currency: string }
  estimateToken?: string
  expiresAt?: string
}
export interface GenerationAccepted {
  id: string
  resourceType: 'generation'
  status: 'accepted'
  revision: string
}
export const validateGeneration = (data: GenerationSubmission, signal: AbortSignal) =>
  request<{ code: number; data: GenerationValidation }>({
    url: '/api/v1/generations/validate',
    method: 'post',
    data,
    signal,
  })
export const submitGeneration = (data: GenerationSubmission, key: string) =>
  request<{ code: number; data: GenerationAccepted }>({
    url: '/api/v1/generations',
    method: 'post',
    data,
    headers: { 'Idempotency-Key': key },
  })

export async function subscribeGeneration(
  id: string,
  cursor: string | undefined,
  signal: AbortSignal,
  receive: (event: ServerEvent) => Promise<void>,
  opened: () => void = () => {},
) {
  const body = await requestEventStream(`/api/v1/generations/${id}/events`, cursor, signal)
  opened()
  for await (const event of parseEventStream(body)) {
    if (signal.aborted) return
    await receive(event)
  }
}

export interface GenerationOutput {
  id: string
  jobId: string
  ordinal: number
  kind: 'image' | 'video' | 'text'
  workStatus: 'none' | 'working' | 'review' | 'approved' | 'rejected'
  actualMetadata: {
    width?: number
    height?: number
    durationSeconds?: string
    format?: string
    revisedPrompt?: string
  }
  archiveState:
    | 'not_started'
    | 'archiving'
    | 'archived'
    | 'archive_failed'
    | 'source_expired'
    | 'not_applicable'
  revision: string
  text?: string
  file?: { id: string; state: 'ready' | 'unavailable'; mimeType: string; byteSize: string }
  previewUrl?: string
  downloadUrl?: string
  allowedActions: string[]
}
export const updateOutputStatus = (
  id: string,
  data: { revision: string; workStatus: GenerationOutput['workStatus']; reason: string },
  key: string,
  signal?: AbortSignal,
) => request<{ code: number; data: GenerationOutput }>({
  url: `/api/v1/outputs/${encodeURIComponent(id)}/work-status`, method: 'post', data, signal,
  headers: { 'Idempotency-Key': key },
})
export interface GenerationSnapshot extends GenerationSummary {
  diagnostic?: { code: string; phase: 'prepare' | 'submit' | 'poll'; message: string } | null
  sourceJobId?: string | null
  elementDestination?: { id: string; projectId: string; name: string } | null
  cancelState: 'none' | 'requested' | 'confirmed' | 'rejected' | 'unsupported'
  updateTime: string
  model: { id: string; versionId: string; displayName: string }
  outputs: GenerationOutput[]
  outputsVisibility: 'visible' | 'hidden'
  usageState: 'unknown' | 'partial' | 'available'
  billingVisibility: 'unavailable' | 'hidden' | 'visible'
  billing?: {
    platform: { amount: string | null; currency: string; state: GenerationSummary['billingState'] }
    usage: {
      subjects: {
        subjectId: string
        inputTokens: string | null
        outputTokens: string | null
        videoTokens: string | null
        imageCount: number | null
        outputSeconds: string | null
        referenceSeconds: string | null
      }[]
    }
  }
  eventCursor: string
}
export function cancelGeneration(
  id: string,
  data: { revision: string; reason: string },
  key: string,
  signal?: AbortSignal,
) {
  return request<{ code: number; data: { task: GenerationSnapshot } }>({
    url: `/api/v1/generations/${id}/cancel`,
      signal,
    method: 'post',
    data,
    headers: { 'Idempotency-Key': key },
  })
}
export interface GenerationInput {
  prompt: DraftBody['prompt']
  parameters: Record<string, unknown>
  references: DraftReference[]
  modelVersionId: string
  createTime: string
}
export const getGeneration = (id: string, signal: AbortSignal) =>
  request<{ code: number; data: GenerationSnapshot }>({ url: `/api/v1/generations/${id}`, signal })
export const getGenerationInput = (id: string, signal: AbortSignal) =>
  request<{ code: number; data: GenerationInput }>({
    url: `/api/v1/generations/${id}/input`,
    signal,
  })
export const getOutputMedia = (id: string, download: boolean, signal: AbortSignal) =>
  requestBlob({ url: `/api/v1/outputs/${id}/${download ? 'download' : 'preview'}`, signal })
export const getOutputThumbnail = (id: string, signal: AbortSignal) =>
  requestBlob({ url: `/api/v1/outputs/${id}/thumbnail`, signal })
export const getOutput = (id: string, signal: AbortSignal) =>
  request<{ code: number; data: GenerationOutput }>({ url: `/api/v1/outputs/${id}`, signal })

export type GenerationState =
  | 'accepted'
  | 'preparing'
  | 'submitting'
  | 'submission_unknown'
  | 'running'
  | 'finished'
  | 'blocked'
export type GenerationKind = 'image' | 'video' | 'chat'
export interface GenerationSummary {
  id: string
  projectId: string
  projectName?: string
  cardPreview?: { outputId: string; revision: string; kind: 'image' | 'video' }
  billingVisibility?: 'visible' | 'hidden' | 'unavailable'
  billingSummary?: { amount: string | null; currency: string; state: 'pending' | 'calculated' | 'confirmed' | 'disputed' }
  kind: GenerationKind
  createTime: string
  revision: string
  orchestrationState: GenerationState
  upstreamState:
    'not_submitted' | 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'unknown'
  archiveSummary: { total: number; ready: number; failed: number; pending: number }
  billingState: 'pending' | 'calculated' | 'confirmed' | 'disputed'
  allowedActions: string[]
}
export interface GenerationQuery {
  scope: 'mine' | 'project'
  projectId?: string
  kind?: GenerationKind
  state?: GenerationState
  from?: string
  to?: string
  pageNum: number
  pageSize: number
}
export function listGenerations(params: GenerationQuery, signal?: AbortSignal) {
  return request<{ code: number; rows: GenerationSummary[]; total: number; hasNext: boolean }>({
    url: '/api/v1/generations',
    params,
    signal,
  })
}
