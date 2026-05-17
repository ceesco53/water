import clsx from 'clsx'

type StatusLevel = 'ok' | 'warn' | 'danger' | 'unknown'

interface Props {
  title: string
  icon: string
  status: StatusLevel
  primary: string
  secondary?: string
  detail?: string
  note?: string
}

const statusColors: Record<StatusLevel, string> = {
  ok: 'border-green-500/40 bg-green-900/10',
  warn: 'border-yellow-500/40 bg-yellow-900/10',
  danger: 'border-red-500/40 bg-red-900/10',
  unknown: 'border-slate-700 bg-surface-card',
}

const dotColors: Record<StatusLevel, string> = {
  ok: 'bg-green-400',
  warn: 'bg-yellow-400',
  danger: 'bg-red-400 animate-pulse',
  unknown: 'bg-slate-500',
}

export function SignalCard({ title, icon, status, primary, secondary, detail, note }: Props) {
  return (
    <div className={clsx('rounded-xl border p-4 flex flex-col gap-2', statusColors[status])}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg">{icon}</span>
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{title}</span>
        </div>
        <span className={clsx('w-2 h-2 rounded-full flex-shrink-0', dotColors[status])} />
      </div>

      <div>
        <div className="text-2xl font-bold text-slate-100 tabular-nums">{primary}</div>
        {secondary && <div className="text-sm text-slate-400 mt-0.5">{secondary}</div>}
      </div>

      {detail && <div className="text-xs text-slate-500">{detail}</div>}
      {note && (
        <div className="text-xs text-slate-600 border-t border-surface-border pt-2 mt-1 italic">
          {note}
        </div>
      )}
    </div>
  )
}
