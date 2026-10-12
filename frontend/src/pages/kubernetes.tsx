import { cn } from 'cn'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { SectionLabel } from '@/components/vyom/section-label'
import { StatusBadge } from '@/components/vyom/status-badge'
import { StatusText } from '@/components/vyom/status-text'
import { Ticker } from '@/components/vyom/ticker'
import { evidenceTone, type Evidence } from '@/lib/agent'
import { clockTime } from '@/lib/api-health'
import { PODS_REFRESH_SECONDS, podTone, usePods } from '@/lib/pods'
import { toneGlyph, toneText, type Tone } from '@/lib/status'

const chip = 'rounded border border-vy-line px-1.5 py-0.5 font-mono text-[10px] text-vy-text-3'

function count(evidence: Evidence, tone: Tone) {
  return evidence.items.filter((item) => podTone(item) === tone).length
}

function PodsTable({ evidence }: { evidence: Evidence }) {
  return (
    <Table aria-label={`Pods in namespace ${evidence.source.namespace}`}>
      <TableHeader>
        <TableRow className="border-vy-line hover:bg-transparent">
          <TableHead>Pod</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Ready</TableHead>
          <TableHead className="text-right">Restarts</TableHead>
          <TableHead>UID</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {evidence.items.map((item) => (
          <TableRow key={item.id} title={item.id}>
            <TableCell className="font-mono text-xs text-vy-text">{item.name}</TableCell>
            <TableCell>
              <StatusBadge
                tone={podTone(item)}
                // Healthy rows stay quiet (DESIGN.md §1): colour is for what needs attention.
                className={cn(
                  'tracking-[0.06em] normal-case',
                  podTone(item) === 'ok' && 'border-vy-quiet-2 bg-transparent text-vy-text-2',
                )}
              >
                {String(item.attributes.status ?? 'unknown')}
              </StatusBadge>
            </TableCell>
            <TableCell className="font-mono text-xs text-vy-text-2">
              {String(item.attributes.ready ?? '')}
            </TableCell>
            <TableCell className="text-right font-mono text-xs text-vy-text-2">
              {String(item.attributes.restarts ?? '')}
            </TableCell>
            <TableCell className="font-mono text-[11px] text-vy-text-4">{item.uid ?? '—'}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

// The deterministic view: pods read by the direct collector. It does not use the agent,
// the model or MCP, and it keeps working when they are down.
export function Kubernetes() {
  const pods = usePods()
  const evidence = pods.view?.evidence ?? undefined
  const tone = evidence ? evidenceTone[evidence.state] : 'idle'
  const usable = evidence && ['complete', 'partial', 'zero'].includes(evidence.state)

  return (
    <>
      <Ticker
        aside={evidence ? `Collected ${clockTime(Date.parse(evidence.collected_at))}` : undefined}
      >
        <span className="vy-label tracking-[0.12em] text-vy-text-3">Kubernetes</span>
        {usable ? (
          <>
            <StatusText tone="ok">{count(evidence, 'ok')} nominal</StatusText>
            <StatusText tone="caution">{count(evidence, 'caution')} caution</StatusText>
            <StatusText tone="alert">{count(evidence, 'alert')} alert</StatusText>
          </>
        ) : (
          <StatusText tone={pods.failed || evidence ? 'alert' : 'idle'}>
            {pods.pending ? 'Reading pods' : 'Pods not available'}
          </StatusText>
        )}
      </Ticker>

      <div className="flex max-w-190 min-w-0 flex-col gap-3">
        <SectionLabel number="02">Kubernetes · pods</SectionLabel>
        <h1 className="text-[32px] leading-[1.1] font-semibold tracking-[-0.02em] text-balance">
          {evidence ? (
            <>
              Pods in <span className="font-mono text-[28px]">{evidence.source.namespace}</span>
            </>
          ) : (
            'Pods'
          )}
        </h1>
        <p className="text-base leading-[1.55] text-vy-text-2">
          Read straight from the Kubernetes API by Vyom's collector, with its own read-only
          identity, every {PODS_REFRESH_SECONDS} seconds. This view does not use the agent or MCP.
        </p>
      </div>

      {pods.failed ? (
        <Alert variant="destructive" className="border-vy-alert/35 bg-vy-alert/8">
          <AlertTitle>The pods could not be fetched: {pods.failed}</AlertTitle>
          <AlertDescription>
            {evidence && pods.fetchedAt
              ? `Below is the last read, from ${clockTime(pods.fetchedAt)}. It is stale.`
              : `This page retries every ${PODS_REFRESH_SECONDS} seconds.`}
          </AlertDescription>
        </Alert>
      ) : null}

      <section
        aria-label="Pods"
        className="flex flex-col gap-4 rounded-lg border border-vy-line bg-vy-surface-2 p-5"
      >
        {pods.pending ? (
          <span role="status" className="text-sm text-vy-text-2">
            Reading pods…
          </span>
        ) : !evidence ? (
          <p className="max-w-[68ch] text-sm leading-[1.55] text-vy-text-3">
            {pods.view && !pods.view.configured
              ? 'The backend has no Kubernetes collector configured, so there is nothing to show. Start it with scripts/dev-up.sh to connect it to the Kind cluster.'
              : 'No read is available.'}
          </p>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-1.5">
              <span className={chip}>
                {evidence.source.path} · {evidence.source.collector ?? evidence.source.mcp?.tool_id}
              </span>
              <span className={chip}>
                {evidence.source.connection_id} / ns {evidence.source.namespace}
              </span>
              <span className={cn(chip, toneText[pods.failed ? 'caution' : tone])}>
                <span aria-hidden="true">{toneGlyph[pods.failed ? 'caution' : tone]} </span>
                {pods.failed ? 'stale' : evidence.state}
                {evidence.coverage.truncated ? ' · truncated' : ''}
              </span>
              <span className={chip}>{evidence.coverage.returned} pods</span>
            </div>
            {evidence.errors.map((error) => (
              <span key={error.kind} role="alert" className="text-sm leading-normal text-vy-alert">
                {error.message} <span className="font-mono text-[11px]">({error.kind})</span>
              </span>
            ))}
            {evidence.state === 'partial' ? (
              <span className="text-sm text-vy-caution">
                This list is incomplete: some pods may be missing from it.
              </span>
            ) : null}
            {evidence.state === 'zero' ? (
              <span className="text-sm text-vy-text-2">
                The read completed and found no pods in this namespace.
              </span>
            ) : null}
            {evidence.items.length > 0 ? <PodsTable evidence={evidence} /> : null}
          </>
        )}
      </section>
    </>
  )
}
