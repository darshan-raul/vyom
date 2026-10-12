import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { AskVyom } from '@/components/vyom/ask-vyom'
import { PipelineStrip, type Stage } from '@/components/vyom/pipeline-strip'
import { SectionLabel } from '@/components/vyom/section-label'
import { StatusText } from '@/components/vyom/status-text'
import { evidenceTone, useAgentStatus, useAsk, type AgentStatus, type Ask } from '@/lib/agent'
import { apiLabel, apiTone, clockTime, type ApiHealth } from '@/lib/api-health'
import type { Tone } from '@/lib/status'

function greeting() {
  const hour = new Date().getHours()
  return hour < 12 ? 'Good morning.' : hour < 17 ? 'Good afternoon.' : 'Good evening.'
}

function headline(api: ApiHealth, agent?: AgentStatus) {
  if (api.state === 'unreachable') return 'The API is not answering.'
  if (api.state === 'checking' || !agent) return 'Checking the API.'
  return agent.configured
    ? 'The API is up and the agent is ready.'
    : 'The API is up. The agent is not configured.'
}

// "Configured" is not "healthy": the agent's tone comes from the last question, if any.
function agentState(agent: AgentStatus | undefined, chat: Ask): { tone: Tone; label: string } {
  if (!agent?.configured) return { tone: 'idle', label: 'Agent not connected' }
  if (!chat.result) return { tone: 'idle', label: 'Agent configured' }
  return chat.result.outcome === 'answered'
    ? { tone: 'ok', label: 'Agent answered' }
    : { tone: 'caution', label: 'Agent gave no answer' }
}

// The path a question takes. A stage is drawn nominal or failed only from a real exchange;
// until one happens it shows what is configured, and later stages show their sprint.
function stages(api: ApiHealth, agent: AgentStatus | undefined, chat: Ask): Stage[] {
  const result = chat.result
  const evidence = result?.evidence[0]
  const modelFailed = result?.outcome === 'model_unavailable'
  const modelAnswered = result !== undefined && !modelFailed && result.outcome !== 'timeout'

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
    {
      code: 'REASON',
      name: 'Model and graph',
      detail: !agent?.model
        ? 'not configured'
        : modelFailed
          ? `${agent.model.model} · unavailable`
          : `${agent.model.model} · ${modelAnswered ? 'replied' : 'configured'}`,
      tone: modelFailed ? 'alert' : modelAnswered ? 'ok' : 'idle',
    },
    {
      code: 'K8S MCP',
      name: 'Cluster reads',
      detail: evidence
        ? `${evidence.state} · ${evidence.coverage.returned} items · ${clockTime(Date.parse(evidence.collected_at))}`
        : agent?.tools.length
          ? `${agent.tools.length} tool enabled · ns ${agent.scope?.namespace ?? '?'}`
          : 'not configured',
      tone: evidence ? evidenceTone[evidence.state] : 'idle',
    },
    { code: 'AWS MCP', name: 'Account reads', detail: 'not built · S2', tone: 'idle' },
    { code: 'GROUND', name: 'Runbooks', detail: 'not built · S3', tone: 'idle' },
  ]
}

export function Today({ api }: { api: ApiHealth }) {
  const agent = useAgentStatus(api.state === 'ok')
  const chat = useAsk()
  const state = agentState(agent, chat)

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-vy-line-faint pb-3.5">
        <div className="flex flex-wrap gap-x-4.5 gap-y-1">
          <span className="vy-label tracking-[0.12em] text-vy-text-3">Today</span>
          <StatusText tone={apiTone(api)}>{apiLabel(api)}</StatusText>
          <StatusText tone={state.tone}>{state.label}</StatusText>
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
          {greeting()} {headline(api, agent)}
        </h1>
        {api.state === 'unreachable' ? (
          <Alert variant="destructive" className="border-vy-alert/35 bg-vy-alert/8">
            <AlertTitle>{api.message}</AlertTitle>
            <AlertDescription>
              Start the backend on <span className="font-mono text-[13px]">127.0.0.1:8000</span>.
              This page retries every 10 seconds.
            </AlertDescription>
          </Alert>
        ) : agent?.configured && agent.scope ? (
          <p className="text-base leading-[1.55] text-vy-text-2">
            Vyom can read the pods in namespace{' '}
            <span className="font-mono text-sm text-vy-text">{agent.scope.namespace}</span> through
            the Kubernetes MCP server and answer from what it reads. This console shows only what
            the backend reports; nothing here is sample data.
          </p>
        ) : (
          <p className="text-base leading-[1.55] text-vy-text-2">
            This console shows only what the backend reports. Today that is the liveness of the API
            process: no model or tool is configured, so there is nothing to ask yet.
          </p>
        )}
      </div>

      <AskVyom
        agent={agent}
        chat={chat}
        unavailable={
          api.state === 'unreachable'
            ? 'The backend is unreachable, so nothing can be sent.'
            : 'The backend has no agent configuration (a model and at least one enabled tool), so nothing can be sent. Start it with scripts/chat-up.sh to connect it to the Kind cluster.'
        }
      />

      <PipelineStrip label="Question path" stages={stages(api, agent, chat)} />
    </>
  )
}
