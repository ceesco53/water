import { CircleCheck, CircleHelp, Info, OctagonAlert, TriangleAlert, type LucideIcon } from 'lucide-react'
import type { FindingLevel, Verdict } from './types'

export type StatusLevel = 'ok' | 'warn' | 'danger' | 'unknown' | 'note'

// Status colors are reserved for state and always travel with an icon and a
// label, so meaning never rests on color alone.
export const STATUS: Record<StatusLevel, { label: string; icon: LucideIcon; text: string; bg: string; fill: string }> = {
  ok: { label: 'Good', icon: CircleCheck, text: 'text-status-good', bg: 'bg-status-good/10', fill: 'bg-status-good' },
  warn: { label: 'Watch', icon: TriangleAlert, text: 'text-status-warning', bg: 'bg-status-warning/15', fill: 'bg-status-warning' },
  danger: { label: 'Alert', icon: OctagonAlert, text: 'text-status-critical', bg: 'bg-status-critical/10', fill: 'bg-status-critical' },
  unknown: { label: 'No data', icon: CircleHelp, text: 'text-muted', bg: 'bg-surface-2', fill: 'bg-muted' },
  // Worth knowing, not a warning: neutral accent, never a status color
  note: { label: 'Note', icon: Info, text: 'text-accent', bg: 'bg-accent/10', fill: 'bg-accent' },
}

// The verdict, phrased as advice for the hero
export const VERDICT: Record<Verdict, { status: StatusLevel; headline: string; label: string; stroke: string }> = {
  good: { status: 'ok', headline: 'Good day for a swim', label: 'Good', stroke: 'rgb(var(--good))' },
  caution: { status: 'warn', headline: 'Swim with caution today', label: 'Caution', stroke: 'rgb(var(--warning))' },
  avoid: { status: 'danger', headline: 'Stay out of the water today', label: 'Stay out', stroke: 'rgb(var(--critical))' },
}

// What each finding level means, as a status pill
export const LEVEL: Record<FindingLevel, { status: StatusLevel; label: string }> = {
  avoid: { status: 'danger', label: 'Stay out' },
  caution: { status: 'warn', label: 'Caution' },
  note: { status: 'note', label: 'Note' },
  clear: { status: 'ok', label: 'Clear' },
}
