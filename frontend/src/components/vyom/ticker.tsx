import type { ReactNode } from 'react'

// Header ticker at the top of a page (DESIGN.md §3): mono status on the left, a time on the right.
export function Ticker({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-vy-line-faint pb-3.5">
      <div className="flex flex-wrap gap-x-4.5 gap-y-1">{children}</div>
      {aside ? <span className="vy-label tracking-[0.1em] text-vy-text-4">{aside}</span> : null}
    </div>
  )
}
