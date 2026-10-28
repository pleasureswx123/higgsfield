import type { AssetWorkStatus } from '@/api/assets'
export const assetStatuses: { value: AssetWorkStatus; label: string; color: string }[] = [
  { value: 'working', label: '进行中', color: '#389cf5' },
  { value: 'review', label: '待审核', color: '#f28c00' },
  { value: 'approved', label: '已通过', color: '#c8f000' },
  { value: 'rejected', label: '已驳回', color: '#ef4444' },
]
export const assetStatus = (value?: AssetWorkStatus) => assetStatuses.find(item => item.value === value)
