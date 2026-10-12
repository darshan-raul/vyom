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

// Status tint recipe (DESIGN.md §2.1): status-colour text, ~35% border, ~8% fill.
export const toneTint: Record<Tone, string> = {
  ok: 'border-vy-ok/35 bg-vy-ok/8 text-vy-ok',
  caution: 'border-vy-caution/35 bg-vy-caution/8 text-vy-caution',
  alert: 'border-vy-alert/35 bg-vy-alert/8 text-vy-alert',
  idle: 'border-vy-line-strong bg-transparent text-vy-text-3',
}
