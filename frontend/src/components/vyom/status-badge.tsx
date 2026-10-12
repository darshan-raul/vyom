import type { ComponentProps } from 'react'
import { cn } from 'cn'

import { toneGlyph, toneTint, type Tone } from '@/lib/status'

// Mono 10px uppercase badge with a glyph: `■ ALERT`, `▲ CAUTION`, `● NOMINAL` (DESIGN.md §4).
export function StatusBadge({
  tone,
  className,
  children,
  ...props
}: ComponentProps<'span'> & { tone: Tone }) {
  return (
    <span
      className={cn(
        'vy-micro inline-flex items-center gap-1.5 rounded border px-2 py-1 whitespace-nowrap',
        toneTint[tone],
        className,
      )}
      {...props}
    >
      <span aria-hidden="true">{toneGlyph[tone]}</span>
      {children}
    </span>
  )
}
