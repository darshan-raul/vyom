import { cn } from 'cn'

import { toneBorderTop, toneText, type Tone } from '@/lib/status'

export type Stage = { code: string; name: string; detail: string; tone: Tone }

// Equal cells, each with a 2px top border in its status colour (DESIGN.md §4).
export function PipelineStrip({ label, stages }: { label: string; stages: Stage[] }) {
  return (
    <ol
      aria-label={label}
      className="grid grid-cols-2 overflow-hidden rounded-md border border-vy-line bg-vy-line gap-px sm:grid-cols-3 lg:grid-cols-5"
    >
      {stages.map((stage, index) => (
        <li
          key={stage.code}
          className={cn(
            'flex min-w-0 flex-col gap-1.5 border-t-2 bg-vy-surface-1 px-4 py-3.5',
            toneBorderTop[stage.tone],
          )}
        >
          <span className={cn('vy-micro tracking-[0.14em]', toneText[stage.tone])}>
            {String(index + 1).padStart(2, '0')} {stage.code}
          </span>
          <span className="text-sm font-medium">{stage.name}</span>
          <span className="truncate font-mono text-[11px] text-vy-text-3">{stage.detail}</span>
        </li>
      ))}
    </ol>
  )
}
