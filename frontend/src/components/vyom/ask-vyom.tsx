import { useState, type FormEvent } from 'react'
import { cn } from 'cn'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Answer } from '@/components/vyom/answer'
import type { AgentStatus, Ask } from '@/lib/agent'

// The agent panel (DESIGN.md §4.1). It sends a question and nothing else: scope and tools
// are the server's, and are shown here, not chosen.
export function AskVyom({
  agent,
  chat,
  unavailable,
}: {
  agent?: AgentStatus
  chat: Ask
  unavailable: string // why nothing can be sent, when the agent is not ready
}) {
  const [question, setQuestion] = useState('')
  const ready = agent?.configured === true
  const limit = agent?.max_question_chars ?? 500
  const suggestion = agent?.scope
    ? `Which pods are unhealthy in the ${agent.scope.namespace} namespace?`
    : undefined
  const sendable = ready && !chat.pending && question.trim().length > 0

  const submit = (event?: FormEvent) => {
    event?.preventDefault()
    if (sendable) chat.ask(question.trim())
  }

  return (
    <section
      aria-label="Ask Vyom"
      className="flex flex-wrap rounded-[10px] border border-vy-agent-line bg-linear-to-b from-vy-agent-bg to-vy-agent-bg-2 shadow-[0_24px_60px_-30px_--alpha(var(--color-vy-agent)/35%)]"
    >
      <div className="flex min-w-0 flex-[3_1_520px] flex-col gap-4 px-6 py-5.5">
        <div className="flex flex-wrap items-center justify-between gap-2.5">
          <span className="vy-label flex items-center gap-2.5 text-vy-agent">
            <span
              aria-hidden="true"
              className={cn(
                'size-2 rounded-full',
                ready ? 'vy-live-dot bg-current' : 'border border-current',
              )}
            />
            Ask Vyom · {ready ? 'agent ready' : 'agent not connected'}
          </span>
          <span className="font-mono text-[11px] text-vy-text-4">
            read-only · cites every answer
          </span>
        </div>

        <form
          onSubmit={submit}
          className="flex flex-col rounded-lg border border-vy-agent-line bg-vy-surface-1"
        >
          <label htmlFor="vy-ask" className="sr-only">
            Ask Vyom a question
          </label>
          <Textarea
            id="vy-ask"
            rows={2}
            disabled={!ready}
            maxLength={limit}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                submit()
              }
            }}
            aria-describedby="vy-ask-state"
            placeholder={suggestion ?? 'Which pods are unhealthy?'}
            className="rounded-none border-0 px-4.5 pt-4 pb-1.5 text-[17px] leading-normal focus-visible:ring-0"
          />
          <div className="flex flex-wrap items-center justify-between gap-2.5 py-2 pr-2.5 pl-4.5">
            <span className="flex flex-wrap gap-x-3.5 gap-y-1 font-mono text-[11px] text-vy-text-3">
              <span>
                scope:{' '}
                <span className="text-vy-text">
                  {agent?.scope
                    ? `${agent.scope.connection_id} / ns ${agent.scope.namespace}`
                    : 'set by the server'}
                </span>
              </span>
              <span>
                tools:{' '}
                {agent?.tools.length ? (
                  <span className="text-vy-text">
                    {agent.tools.map((tool) => tool.id).join(' · ')}
                  </span>
                ) : (
                  <span className="text-vy-text-4">none connected</span>
                )}
              </span>
            </span>
            <Button type="submit" variant="agent" disabled={!sendable}>
              {chat.pending ? 'Asking…' : 'Ask ↵'}
            </Button>
          </div>
        </form>

        {ready ? (
          <div id="vy-ask-state" className="flex flex-col gap-2">
            <span className="vy-micro tracking-[0.14em] text-vy-text-4">
              What it can answer now
            </span>
            <div className="flex flex-wrap items-center gap-2">
              {suggestion ? (
                <button
                  type="button"
                  onClick={() => setQuestion(suggestion)}
                  className="min-h-9 rounded-full border border-vy-agent-line bg-vy-agent-bg px-3 py-1.5 text-left text-[13px] text-vy-text-2 hover:bg-vy-surface-sel"
                >
                  {suggestion}
                </button>
              ) : null}
              <span className="text-xs text-vy-text-4">
                One read of the pods in this namespace per question.
              </span>
            </div>
          </div>
        ) : (
          <p id="vy-ask-state" className="max-w-[68ch] text-[13px] leading-[1.55] text-vy-text-3">
            {unavailable}
          </p>
        )}
      </div>

      <div
        aria-live="polite"
        className="flex min-w-0 flex-[2_1_340px] flex-col gap-3 border-t border-vy-agent-line/60 px-6 py-5.5 lg:border-t-0 lg:border-l"
      >
        <Answer chat={chat} />
      </div>
    </section>
  )
}
