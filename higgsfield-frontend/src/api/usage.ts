import { request } from './client'

export type UsageGroup = 'project' | 'user' | 'department' | 'model' | 'day'
export interface UsageSummaryRow {
  groupKey: string
  displayName: string
  currency: string
  calculatedAmount: string
  confirmedAmount: string
  disputedAmount: string
  totalKnownAmount: string
  unknownCount: string
  inputTokens: string
  outputTokens: string
  videoTokens: string
  usageCompleteness: 'available' | 'partial' | 'unknown'
}
export interface UsageSummary {
  timeBasis: 'createTime'
  businessTimezone: string
  purpose: 'platform'
  rows: UsageSummaryRow[]
}
export interface UsageSummaryQuery {
  from: string
  to: string
  groupBy: UsageGroup
  timeBasis: 'createTime'
  purpose: 'platform'
  businessTimezone: 'Asia/Shanghai'
}
export const getPersonalUsageSummary = (params: UsageSummaryQuery, signal: AbortSignal) =>
  request<{ code: number; data: UsageSummary }>({
    url: '/api/v1/me/usage/summary',
    params,
    signal,
  })

export const getProjectUsageSummary = (
  projectId: string,
  params: UsageSummaryQuery,
  signal: AbortSignal,
) =>
  request<{ code: number; data: UsageSummary }>({
    url: `/api/v1/projects/${encodeURIComponent(projectId)}/usage/summary`,
    params,
    signal,
  })

export interface BudgetPeriodStatus {
  id: string
  budgetId: string
  purpose: 'platform'
  currency: string
  periodStart: string
  periodEnd: string | null
  limitAmount: string
  reservedAmount: string
  consumedAmount: string
  availableAmount: string
  revision: string
}

export interface BudgetStatus {
  canSubmit: boolean
  blockingCodes: string[]
  amountVisibility: 'visible' | 'hidden'
  periods?: BudgetPeriodStatus[]
}

export const getBudgetStatus = (projectId: string, signal: AbortSignal) =>
  request<{ code: number; data: BudgetStatus }>({
    url: `/api/v1/projects/${projectId}/budget-status`,
    signal,
  })
