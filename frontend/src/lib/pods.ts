import { useCustom } from '@refinedev/core'

import type { Evidence, EvidenceItem } from '@/lib/agent'
import type { Tone } from '@/lib/status'

// Shape of GET /api/kubernetes/pods: the direct collector's read, independent of the agent.
export type PodsView = {
  configured: boolean
  evidence: Evidence | null
  persisted?: boolean | null
}

export type Pods = {
  view?: PodsView // the last successful response, kept while a later fetch fails
  pending: boolean
  failed?: string // the latest fetch failed; `view`, if any, is from `fetchedAt`
  fetchedAt?: number
}

export const PODS_REFRESH_SECONDS = 15

export function usePods(): Pods {
  const { query } = useCustom<PodsView>({
    url: '/api/kubernetes/pods',
    method: 'get',
    queryOptions: { retry: false, refetchInterval: PODS_REFRESH_SECONDS * 1000 },
    errorNotification: false,
  })
  return {
    view: query.data?.data,
    pending: query.isPending,
    failed: query.isError ? query.error.message : undefined,
    fetchedAt: query.dataUpdatedAt || undefined,
  }
}

// How a pod row is drawn. The evidence itself is shown unchanged beside it.
export function podTone(item: EvidenceItem): Tone {
  const status = String(item.attributes.status ?? '')
  const [ready, wanted] = String(item.attributes.ready ?? '').split('/')
  if (status === 'Completed') return 'ok'
  if (status === 'Running') return ready === wanted ? 'ok' : 'caution'
  if (status === 'Pending' || status === 'ContainerCreating') return 'caution'
  return 'alert'
}
