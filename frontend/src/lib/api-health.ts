import { useCustom } from '@refinedev/core'

import type { Tone } from '@/lib/status'

type Health = { status: string; service: string; version: string }

export type ApiHealth =
  | { state: 'checking' }
  | { state: 'unreachable'; message: string; checkedAt: number }
  | { state: 'ok'; status: string; service: string; version: string; checkedAt: number }

// Process liveness of the API only: it says nothing about Kubernetes, MCP or the model.
export function useApiHealth(): ApiHealth {
  const { query } = useCustom<Health>({
    url: '/api/health',
    method: 'get',
    queryOptions: { retry: false, refetchInterval: 10_000 },
    errorNotification: false,
  })
  if (query.isError) {
    return { state: 'unreachable', message: query.error.message, checkedAt: query.errorUpdatedAt }
  }
  const health = query.data?.data
  if (!health) return { state: 'checking' }
  return { state: 'ok', ...health, checkedAt: query.dataUpdatedAt }
}

export const apiTone = (api: ApiHealth): Tone =>
  api.state === 'ok' ? 'ok' : api.state === 'unreachable' ? 'alert' : 'idle'

export const apiLabel = (api: ApiHealth): string =>
  api.state === 'ok' ? 'API nominal' : api.state === 'unreachable' ? 'API unreachable' : 'Checking API'

export const clockTime = (timestamp: number): string =>
  new Date(timestamp).toLocaleTimeString('en-GB', { hour12: false })
