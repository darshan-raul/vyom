import { cn } from 'cn'

import { StatusText } from '@/components/vyom/status-text'
import { clockTime } from '@/lib/api-health'
import {
  evidenceTone,
  outcomeLabel,
  type Ask,
  type ChatResult,
  type Evidence,
} from '@/lib/agent'
import { podTone } from '@/lib/pods'
import { toneGlyph, toneText } from '@/lib/status'

// The answer with each "[n]" drawn as a citation that names the item it points at.
function CitedText({ result }: { result: ChatResult }) {
  const items = new Map(result.evidence.flatMap((e) => e.items).map((item) => [item.id, item]))
  const cited = new Map(result.citations.map((c) => [c.ref, items.get(c.item_id)]))

  return (
    <p className="text-sm leading-[1.6] whitespace-pre-wrap text-vy-text">
      {(result.answer ?? '').split(/(\[\d+\])/).map((part, index) => {
        const ref = /^\[(\d+)\]$/.exec(part)
        if (!ref) return part
        const item = cited.get(Number(ref[1]))
        return (
          <sup
            key={index}
            title={item ? `${item.kind} ${item.name}` : undefined}
            className="font-mono text-[10px] text-vy-agent"
          >
            {part}
          </sup>
        )
      })}
    </p>
  )
}

function EvidenceBlock({ evidence, refs }: { evidence: Evidence; refs: Map<string, number> }) {
  const tone = evidenceTone[evidence.state]
  const chip = 'rounded border border-vy-line px-1.5 py-0.5 font-mono text-[10px] text-vy-text-3'

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className={chip}>{evidence.source.mcp?.tool_id ?? evidence.source.path}</span>
        <span className={chip}>ns {evidence.source.namespace}</span>
        <span className={chip}>collected {clockTime(Date.parse(evidence.collected_at))}</span>
        <span className={cn(chip, toneText[tone])}>
          <span aria-hidden="true">{toneGlyph[tone]} </span>
          {evidence.state}
          {evidence.coverage.truncated ? ' · truncated' : ''}
        </span>
      </div>
      {evidence.errors.map((error) => (
        <span key={error.kind} className="text-[13px] leading-normal text-vy-alert">
          {error.message} <span className="font-mono text-[11px]">({error.kind})</span>
        </span>
      ))}
      {evidence.items.length > 0 ? (
        <ul className="overflow-hidden rounded-md border border-vy-line bg-vy-surface-1">
          {evidence.items.map((item) => {
            const pod = podTone(item)
            return (
              <li
                key={item.id}
                className="flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5 border-t border-vy-line-faint px-3 py-2 first:border-t-0"
              >
                <span className="w-6 font-mono text-[10px] text-vy-agent">
                  {refs.has(item.id) ? `[${refs.get(item.id)}]` : ''}
                </span>
                <span className="min-w-0 flex-1 font-mono text-xs break-all text-vy-text">
                  {item.name}
                </span>
                <span className={cn('font-mono text-[11px]', pod === 'ok' ? 'text-vy-text-2' : toneText[pod])}>
                  <span aria-hidden="true">{toneGlyph[pod]} </span>
                  {String(item.attributes.status ?? 'unknown')}
                </span>
                <span className="font-mono text-[11px] text-vy-text-3">
                  {String(item.attributes.ready ?? '')} · {String(item.attributes.restarts ?? '?')}↻
                </span>
              </li>
            )
          })}
        </ul>
      ) : null}
    </div>
  )
}

const micro = 'vy-micro tracking-[0.14em] text-vy-text-4'

// The right column of the agent panel: the last question, its answer or the reason there is
// none, and the evidence that was collected either way.
export function Answer({ chat }: { chat: Ask }) {
  const { asked, result } = chat

  if (!asked) {
    return (
      <>
        <span className={micro}>Last answer</span>
        <span className="text-sm text-vy-text-2">No answer yet.</span>
        <p className="text-[13px] leading-[1.6] text-vy-text-3">
          Each answer names the tool that was called, the resources it read and when they were
          collected. If the model or the tool is unavailable, the answer says so instead of
          guessing.
        </p>
      </>
    )
  }

  const question = <span className="text-sm text-vy-text-3">“{asked.question}”</span>
  if (chat.pending) {
    return (
      <>
        <span className={micro}>Asking</span>
        {question}
        <span role="status" className="text-sm text-vy-text-2">
          One model request, one read through the tool, one answer.
        </span>
      </>
    )
  }
  if (!result) {
    return (
      <>
        <span className={micro}>Last answer · {clockTime(asked.at)}</span>
        {question}
        <span role="alert" className="text-sm text-vy-alert">
          The question did not reach the agent: {chat.failed ?? 'unknown error'}.
        </span>
      </>
    )
  }

  const refs = new Map(result.citations.map((citation) => [citation.item_id, citation.ref]))
  return (
    <>
      <span className={micro}>Last answer · {clockTime(asked.at)}</span>
      {question}
      {result.outcome === 'answered' ? (
        <CitedText result={result} />
      ) : (
        <div
          role="status"
          className="flex flex-col gap-1.5 rounded-md border border-vy-caution/35 bg-vy-caution/8 px-3 py-2.5"
        >
          <StatusText tone="caution" className="text-[10px]">
            {outcomeLabel[result.outcome]}
          </StatusText>
          <span className="text-sm leading-normal text-vy-text-2">{result.limitation}</span>
        </div>
      )}
      {result.evidence.length > 0 ? (
        <>
          <span className={cn(micro, 'mt-1')}>Evidence</span>
          {result.evidence.map((evidence) => (
            <EvidenceBlock key={evidence.id} evidence={evidence} refs={refs} />
          ))}
        </>
      ) : null}
      {result.trace_id ? (
        <span className="mt-auto pt-1 font-mono text-[10px] text-vy-text-4">
          trace {result.trace_id}
        </span>
      ) : null}
    </>
  )
}
