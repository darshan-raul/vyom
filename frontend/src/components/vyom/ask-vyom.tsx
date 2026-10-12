import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'

// The agent panel (DESIGN.md §4.1). The chat route does not exist yet, so the form is
// disabled and says so; it never pretends to send a question.
export function AskVyom() {
  return (
    <section
      aria-label="Ask Vyom"
      className="flex flex-wrap rounded-[10px] border border-vy-agent-line bg-linear-to-b from-vy-agent-bg to-vy-agent-bg-2 shadow-[0_24px_60px_-30px_--alpha(var(--color-vy-agent)/35%)]"
    >
      <div className="flex min-w-0 flex-[3_1_520px] flex-col gap-4 px-6 py-5.5">
        <div className="flex flex-wrap items-center justify-between gap-2.5">
          <span className="vy-label flex items-center gap-2.5 text-vy-agent">
            <span aria-hidden="true" className="size-2 rounded-full border border-current" />
            Ask Vyom · agent not connected
          </span>
          <span className="font-mono text-[11px] text-vy-text-4">
            read-only · cites every answer
          </span>
        </div>

        <form
          onSubmit={(event) => event.preventDefault()}
          className="flex flex-col rounded-lg border border-vy-agent-line bg-vy-surface-1"
        >
          <label htmlFor="vy-ask" className="sr-only">
            Ask Vyom a question
          </label>
          <Textarea
            id="vy-ask"
            rows={2}
            disabled
            aria-describedby="vy-ask-state"
            placeholder="Which pods are unhealthy in the demo namespace?"
            className="rounded-none border-0 px-4.5 pt-4 pb-1.5 text-[17px] leading-normal focus-visible:ring-0"
          />
          <div className="flex flex-wrap items-center justify-between gap-2.5 py-2 pr-2.5 pl-4.5">
            <span className="flex flex-wrap gap-x-3.5 gap-y-1 font-mono text-[11px] text-vy-text-3">
              <span>
                scope: <span className="text-vy-text">set by the server</span>
              </span>
              <span>
                tools: <span className="text-vy-text-4">none connected</span>
              </span>
            </span>
            <Button type="submit" variant="agent" disabled>
              Ask ↵
            </Button>
          </div>
        </form>

        <p id="vy-ask-state" className="max-w-[68ch] text-[13px] leading-[1.55] text-vy-text-3">
          The chat route is not built yet, so nothing can be sent from here. The first question
          Vyom will answer is pod health in one namespace, from a live read through the Kubernetes
          MCP server.
        </p>
      </div>

      <div className="flex min-w-0 flex-[2_1_300px] flex-col gap-3 border-t border-vy-agent-line/60 px-6 py-5.5 lg:border-t-0 lg:border-l">
        <span className="vy-micro tracking-[0.14em] text-vy-text-4">Last answer</span>
        <span className="text-sm text-vy-text-2">No answer yet.</span>
        <p className="text-[13px] leading-[1.6] text-vy-text-3">
          Each answer will name the tool that was called, the resources it read and when they were
          collected. If the model or the tool is unavailable, the answer says so instead of
          guessing.
        </p>
      </div>
    </section>
  )
}
