import { cn } from 'cn'

import mark from '@/assets/vyom-mark.png'
import { apiLabel, apiTone, clockTime, type ApiHealth } from '@/lib/api-health'
import { toneText } from '@/lib/status'

// Surfaces in delivery order. `sprint` marks one that is planned but not built:
// it is listed so the console's shape is visible, and it is not a link.
type NavItem = { label: string; sprint?: string }

const operate: NavItem[] = [
  { label: 'Today' },
  { label: 'Kubernetes', sprint: 'S1' },
  { label: 'AWS', sprint: 'S2' },
  { label: 'Findings', sprint: 'S4' },
  { label: 'Spend', sprint: 'S4' },
]

const flightKit: NavItem[] = [
  { label: 'Runbooks', sprint: 'S3' },
  { label: 'History', sprint: 'S3' },
]

function NavRow({ item, number }: { item: NavItem; number?: string }) {
  const row = 'flex min-h-10 items-center gap-3 border-l-2 px-3 text-sm'
  const numberCell = number ? (
    <span className={cn('font-mono text-[10px]', item.sprint ? 'text-vy-quiet' : 'text-vy-caution')}>
      {number}
    </span>
  ) : null

  if (item.sprint) {
    return (
      <li>
        <span
          aria-disabled="true"
          title={`Planned for sprint ${item.sprint}`}
          className={cn(row, 'border-transparent text-vy-text-4')}
        >
          {numberCell}
          <span className="flex-1">{item.label}</span>
          <span className="vy-micro tracking-[0.08em]">
            <span className="sr-only">planned for sprint </span>
            {item.sprint}
          </span>
        </span>
      </li>
    )
  }
  return (
    <li>
      <a
        href="/"
        aria-current="page"
        className={cn(
          row,
          'border-vy-caution bg-linear-to-r from-vy-caution/8 to-transparent font-medium text-vy-text',
        )}
      >
        {numberCell}
        <span className="flex-1">{item.label}</span>
      </a>
    </li>
  )
}

export function Sidebar({ api }: { api: ApiHealth }) {
  const tone = apiTone(api)

  return (
    <nav
      aria-label="Primary"
      className="flex max-w-64 min-w-55 flex-[1_1_232px] flex-col gap-5.5 px-0.5 py-1.5"
    >
      <div className="flex items-center gap-3 px-2 py-1">
        <img
          src={mark}
          alt="Vyom logo"
          className="size-11 rounded-full shadow-[0_0_0_1px_--alpha(var(--color-vy-agent)/25%),0_0_24px_--alpha(var(--color-vy-agent)/30%)]"
        />
        <div className="flex flex-col gap-0.5">
          <span className="text-[19px] leading-none font-bold tracking-[0.22em]">VYOM</span>
          <span className="vy-micro text-vy-text-3">AWS · K8s · Alpha</span>
        </div>
      </div>

      <div className="flex flex-col gap-0.5">
        <span className="vy-micro px-3 py-1.5 tracking-[0.16em] text-vy-text-4">Operate</span>
        <ul className="flex flex-col gap-0.5">
          {operate.map((item, index) => (
            <NavRow key={item.label} item={item} number={String(index + 1).padStart(2, '0')} />
          ))}
        </ul>
      </div>

      <div className="flex flex-col gap-0.5">
        <span className="vy-micro px-3 py-1.5 tracking-[0.16em] text-vy-text-4">Flight kit</span>
        <ul className="flex flex-col gap-0.5">
          {flightKit.map((item) => (
            <NavRow key={item.label} item={item} />
          ))}
        </ul>
      </div>

      <div className="mt-2 flex flex-col gap-2 rounded-md border border-vy-line bg-vy-surface-1 p-3.5">
        <span
          role="status"
          className={cn('vy-label flex items-center gap-2 tracking-[0.1em]', toneText[tone])}
        >
          <span
            aria-hidden="true"
            className={cn(
              'size-[7px] rounded-full',
              tone === 'idle' ? 'border border-current' : 'bg-current',
              tone === 'ok' && 'vy-live-dot',
            )}
          />
          {apiLabel(api)}
        </span>
        <span className="text-xs leading-[1.55] text-vy-text-3">
          Read-only by design: Vyom never writes to your cluster or your AWS account.
          {api.state === 'checking' ? null : (
            <>
              {' '}
              Last check <span className="font-mono text-[11px]">{clockTime(api.checkedAt)}</span>.
            </>
          )}
        </span>
      </div>
    </nav>
  )
}
