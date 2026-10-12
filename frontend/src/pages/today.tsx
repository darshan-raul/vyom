import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { AskVyom } from '@/components/vyom/ask-vyom'
import { PipelineStrip, type Stage } from '@/components/vyom/pipeline-strip'
import { SectionLabel } from '@/components/vyom/section-label'
import { StatusText } from '@/components/vyom/status-text'
import { apiLabel, apiTone, clockTime, type ApiHealth } from '@/lib/api-health'

function greeting() {
  const hour = new Date().getHours()
  return hour < 12 ? 'Good morning.' : hour < 17 ? 'Good afternoon.' : 'Good evening.'
}

const headline: Record<ApiHealth['state'], string> = {
  ok: 'The API is up. The agent is not connected yet.',
  unreachable: 'The API is not answering.',
  checking: 'Checking the API.',
}

// The path a question will take. Only the API reports its own state today; the other
// stages stay "not reported" until the backend exposes them, never assumed healthy.
function stages(api: ApiHealth): Stage[] {
  return [
    {
      code: 'API',
      name: 'Backend',
      detail:
        api.state === 'ok'
          ? `${api.service} ${api.version} · ${api.status}`
          : api.state === 'unreachable'
            ? 'unreachable'
            : 'checking',
      tone: apiTone(api),
    },
    { code: 'REASON', name: 'Model and graph', detail: 'not wired to the API · S1', tone: 'idle' },
    { code: 'K8S MCP', name: 'Cluster reads', detail: 'not wired to the API · S1', tone: 'idle' },
    { code: 'AWS MCP', name: 'Account reads', detail: 'not built · S2', tone: 'idle' },
    { code: 'GROUND', name: 'Runbooks', detail: 'not built · S3', tone: 'idle' },
  ]
}

export function Today({ api }: { api: ApiHealth }) {
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-vy-line-faint pb-3.5">
        <div className="flex flex-wrap gap-x-4.5 gap-y-1">
          <span className="vy-label tracking-[0.12em] text-vy-text-3">Today</span>
          <StatusText tone={apiTone(api)}>{apiLabel(api)}</StatusText>
          <StatusText tone="idle">Agent not connected</StatusText>
        </div>
        {api.state === 'checking' ? null : (
          <span className="vy-label tracking-[0.1em] text-vy-text-4">
            Checked {clockTime(api.checkedAt)}
          </span>
        )}
      </div>

      <div className="flex max-w-190 min-w-0 flex-col gap-3">
        <SectionLabel number="00" className="text-vy-caution">
          Flight status
        </SectionLabel>
        <h1 className="text-[44px] leading-[1.05] font-semibold tracking-[-0.02em] text-balance">
          {greeting()} {headline[api.state]}
        </h1>
        {api.state === 'unreachable' ? (
          <Alert variant="destructive" className="border-vy-alert/35 bg-vy-alert/8">
            <AlertTitle>{api.message}</AlertTitle>
            <AlertDescription>
              Start the backend on <span className="font-mono text-[13px]">127.0.0.1:8000</span>.
              This page retries every 10 seconds.
            </AlertDescription>
          </Alert>
        ) : (
          <p className="text-base leading-[1.55] text-vy-text-2">
            This console shows only what the backend reports. Today that is the liveness of the API
            process. Cluster evidence and cited answers appear here once the chat route and the
            Kubernetes view exist.
          </p>
        )}
      </div>

      <AskVyom />

      <PipelineStrip label="Question path" stages={stages(api)} />
    </>
  )
}
