// Status is never colour-only (DESIGN.md §8): every tone carries a glyph.
// `idle` is "not reported": different from nominal, and never shown as healthy.
export type Tone = 'ok' | 'caution' | 'alert' | 'idle'

export const toneGlyph: Record<Tone, string> = {
  ok: '●',
  caution: '▲',
  alert: '■',
  idle: '○',
}

export const toneText: Record<Tone, string> = {
  ok: 'text-vy-ok',
  caution: 'text-vy-caution',
  alert: 'text-vy-alert',
  idle: 'text-vy-text-4',
}

export const toneBorderTop: Record<Tone, string> = {
  ok: 'border-t-vy-ok',
  caution: 'border-t-vy-caution',
  alert: 'border-t-vy-alert',
  idle: 'border-t-vy-line-strong',
}
