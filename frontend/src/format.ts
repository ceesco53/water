import { format, parseISO } from 'date-fns'

/** '2026-09-30' → 'Sep 30' */
export function shortDate(iso: string): string {
  return format(parseISO(iso), 'MMM d')
}

export function ago(days: number | null): string {
  if (days == null) return ''
  if (days === 0) return 'today'
  return `${days}d ago`
}
