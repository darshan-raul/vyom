import { cn } from 'cn'
import { NavLink } from 'react-router'

import mark from '@/assets/vyom-mark.png'
import { apiLabel, apiTone, clockTime, type ApiHealth } from '@/lib/api-health'
import { toneText } from '@/lib/status'

// Only implemented surfaces have navigation links.
type NavItem = { label: string; to: string }

const operate: NavItem[] = [
  { label: 'Overview', to: '/' },
  { label: 'Kubernetes inventory', to: '/kubernetes' },
]

function NavRow({ item, number }: { item: NavItem; number?: string }) {
  const row = 'flex min-h-10 items-center gap-3 border-l-2 px-3 text-sm'
  return (
    <li>
      <NavLink
        to={item.to}
        end
        className={({ isActive }) =>
          cn(
            row,
            isActive
              ? 'border-vy-caution bg-linear-to-r from-vy-caution/8 to-transparent font-medium text-vy-text'
              : 'border-transparent text-vy-text-2 hover:text-vy-text',
          )
        }
      >
        {({ isActive }) => (
          <>
            {number ? (
              <span
                className={cn(
                  'font-mono text-[10px]',
                  isActive ? 'text-vy-caution' : 'text-vy-quiet',
                )}
              >
                {number}
              </span>
            ) : null}
            <span className="flex-1">{item.label}</span>
          </>
        )}
      </NavLink>
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
          <span className="vy-micro text-vy-text-3">Operations toolkit · Alpha</span>
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
