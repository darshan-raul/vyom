import type { ComponentProps } from 'react'
import { cn } from 'cn'

// Mono uppercase label with an optional number prefix: `01 / POSTURE`.
export function SectionLabel({
  number,
  className,
  children,
  ...props
}: ComponentProps<'span'> & { number?: string }) {
  return (
    <span className={cn('vy-label text-vy-text-3', className)} {...props}>
      {number ? `${number} / ` : null}
      {children}
    </span>
  )
}
