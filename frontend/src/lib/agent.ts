import { useState } from 'react'
import { useCustom, useCustomMutation } from '@refinedev/core'

import type { Tone } from '@/lib/status'

// Shapes of GET /api/agent and POST /api/chat (backend: vyom/api/app.py, vyom/evidence.py).
export type AgentStatus = {
  configured: boolean
  scope: { connection_id: string; namespace: string } | null
  model: { provider: string; model: string } | null
  tools: { id: string; description: string }[]
  max_question_chars: number
}

export type EvidenceState = 'complete' | 'zero' | 'partial' | 'stale' | 'denied' | 'missing'

export type EvidenceItem = {
  id: string
  kind: string
  namespace: string
  name: string
  uid: string | null
  attributes: Record<string, string | number | boolean | null>
}

export type Evidence = {
  id: string
  source: {
    path: 'mcp' | 'direct'
    connection_id: string
    namespace: string
    mcp: { server_id: string; tool_id: string } | null
    collector: string | null
  }
  collected_at: string
  state: EvidenceState
  coverage: { complete: boolean; returned: number; truncated: boolean }
  items: EvidenceItem[]
  errors: { kind: string; message: string }[]
}

export type Outcome =
  | 'answered'
  | 'not_configured'
  | 'no_tool_used'
  | 'no_evidence'
  | 'model_unavailable'
  | 'tool_round_limit'
  | 'invalid_answer'
  | 'timeout'

export type ChatResult = {
  outcome: Outcome
  answer: string | null
  limitation: string | null
  citations: { ref: number; evidence_id: string; item_id: string }[]
  evidence: Evidence[]
  trace_id: string | null
}

// What is configured on the backend. It does not prove the model or the tool is reachable.
export function useAgentStatus(enabled: boolean): AgentStatus | undefined {
  const { query } = useCustom<AgentStatus>({
    url: '/api/agent',
    method: 'get',
    queryOptions: { enabled, retry: false, refetchInterval: 30_000 },
    errorNotification: false,
  })
  return enabled && !query.isError ? query.data?.data : undefined
}

export type Ask = {
  ask: (question: string) => void
  pending: boolean
  asked?: { question: string; at: number }
  result?: ChatResult
  failed?: string // the request itself failed; no result exists
}

export function useAsk(): Ask {
  const { mutate, mutation } = useCustomMutation<ChatResult>()
  const [asked, setAsked] = useState<Ask['asked']>()

  return {
    ask: (question) => {
      setAsked({ question, at: Date.now() })
      mutate({
        url: '/api/chat',
        method: 'post',
        values: { question },
        successNotification: false,
        errorNotification: false,
      })
    },
    pending: mutation.isPending,
    asked,
    result: mutation.isSuccess ? mutation.data.data : undefined,
    failed: mutation.isError ? mutation.error.message : undefined,
  }
}

// Missing, denied, partial and zero stay different (never collapsed into "healthy").
export const evidenceTone: Record<EvidenceState, Tone> = {
  complete: 'ok',
  zero: 'ok',
  partial: 'caution',
  stale: 'caution',
  denied: 'alert',
  missing: 'alert',
}

export const outcomeLabel: Record<Outcome, string> = {
  answered: 'Answered',
  not_configured: 'Not configured',
  no_tool_used: 'Nothing was read',
  no_evidence: 'No evidence',
  model_unavailable: 'Model unavailable',
  tool_round_limit: 'Tool limit reached',
  invalid_answer: 'Answer withheld',
  timeout: 'Timed out',
}
