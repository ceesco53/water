import { CircleCheck, CircleHelp, OctagonAlert, TriangleAlert, type LucideIcon } from 'lucide-react'

export type StatusLevel = 'ok' | 'warn' | 'danger' | 'unknown'

// Status colors are reserved for state and always travel with an icon and a
// label, so meaning never rests on color alone.
export const STATUS: Record<StatusLevel, { label: string; icon: LucideIcon; text: string; bg: string; fill: string }> = {
  ok: { label: 'Good', icon: CircleCheck, text: 'text-status-good', bg: 'bg-status-good/10', fill: 'bg-status-good' },
  warn: { label: 'Watch', icon: TriangleAlert, text: 'text-status-warning', bg: 'bg-status-warning/15', fill: 'bg-status-warning' },
  danger: { label: 'Alert', icon: OctagonAlert, text: 'text-status-critical', bg: 'bg-status-critical/10', fill: 'bg-status-critical' },
  unknown: { label: 'No data', icon: CircleHelp, text: 'text-muted', bg: 'bg-surface-2', fill: 'bg-muted' },
}

// The overall rating, phrased as advice for the hero
export const RATING: Record<string, { status: StatusLevel; verdict: string; stroke: string }> = {
  Excellent: { status: 'ok', verdict: 'Great day for a swim', stroke: 'rgb(var(--good))' },
  Good: { status: 'ok', verdict: 'Good day for a swim', stroke: 'rgb(var(--good))' },
  Caution: { status: 'warn', verdict: 'Swim with caution today', stroke: 'rgb(var(--warning))' },
  'Avoid Swimming': { status: 'danger', verdict: 'Stay out of the water today', stroke: 'rgb(var(--critical))' },
}
