import clsx from 'clsx'
import { STATUS, type StatusLevel } from '../status'

export function StatusPill({ status, label }: { status: StatusLevel; label?: string }) {
  const s = STATUS[status]
  const Icon = s.icon
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium text-ink-2 whitespace-nowrap',
        s.bg
      )}
    >
      <Icon className={clsx('h-3.5 w-3.5', s.text)} aria-hidden strokeWidth={2.25} />
      {label ?? s.label}
    </span>
  )
}
