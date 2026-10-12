import type { ComponentProps } from 'react'
import { cn } from 'cn'

import { toneGlyph, toneText, type Tone } from '@/lib/status'

// Glyph + mono label in the status colour, as used by the header ticker.
export function StatusText({
  tone,
  className,
  children,
  ...props
}: ComponentProps<'span'> & { tone: Tone }) {
  return (
    <span className={cn('vy-label tracking-[0.12em]', toneText[tone], className)} {...props}>
      <span aria-hidden="true">{toneGlyph[tone]} </span>
      {children}
    </span>
  )
}
