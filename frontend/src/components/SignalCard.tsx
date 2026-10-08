import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import type { StatusLevel } from '../status'
import { StatusPill } from './StatusPill'

interface Props {
  title: string
  icon: LucideIcon
  status: StatusLevel
  statusLabel?: string
  value: string
  caption?: string
  detail?: string
  note?: string
  children?: ReactNode
}

export function SignalCard({ title, icon: Icon, status, statusLabel, value, caption, detail, note, children }: Props) {
  return (
    <article className="card flex flex-col gap-3 p-5">
      <header className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="grid h-8 w-8 flex-shrink-0 place-items-center rounded-lg bg-accent/10">
            <Icon className="h-4 w-4 text-accent" aria-hidden strokeWidth={2} />
          </span>
          <h3 className="text-sm font-medium text-ink-2 truncate">{title}</h3>
        </div>
        <StatusPill status={status} label={statusLabel} />
      </header>

      <div>
        <div className="text-[28px] font-semibold leading-tight tracking-tight text-ink">{value}</div>
        {caption && <p className="mt-1 text-sm text-ink-2">{caption}</p>}
      </div>

      {children}

      {(detail || note) && (
        <footer className="mt-auto space-y-1 border-t border-line/10 pt-3">
          {detail && <p className="text-xs text-ink-2">{detail}</p>}
          {note && <p className="text-xs text-muted">{note}</p>}
        </footer>
      )}
    </article>
  )
}
