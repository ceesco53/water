import { CircleCheck } from 'lucide-react'
import type { Finding, Verdict } from '../types'
import { LEVEL, VERDICT } from '../status'
import { StatusPill } from './StatusPill'

const GROUPS: { group: Finding['group']; title: string }[] = [
  { group: 'water', title: 'Water quality' },
  { group: 'hazard', title: 'Weather & safety' },
]

/**
 * Everything behind today's verdict, water and weather kept apart. Findings
 * that matter get their level and reason; clear checks fold into one line.
 */
export function Findings({ verdict, findings }: { verdict: Verdict; findings: Finding[] }) {
  return (
    <section className="card p-5 sm:p-6" aria-labelledby="findings-title">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="findings-title" className="text-base font-semibold text-ink">
          What's behind today's verdict
        </h2>
        <StatusPill status={VERDICT[verdict].status} label={VERDICT[verdict].label} />
      </div>
      <p className="mt-1 text-xs text-ink-2">
        The most serious finding sets the verdict. Notes are worth knowing but don't change it.
      </p>

      {GROUPS.map(({ group, title }) => {
        const items = findings.filter((f) => f.group === group)
        const flagged = items.filter((f) => f.level !== 'clear')
        const clear = items.filter((f) => f.level === 'clear')
        return (
          <div key={group} className="mt-5 border-t border-line/10 pt-4">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">{title}</h3>
            {flagged.length > 0 && (
              <ul className="mt-3 space-y-3">
                {flagged.map((f) => (
                  <li key={f.key} className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-ink">{f.label}</div>
                      <p className="text-xs leading-relaxed text-ink-2">{f.reason}</p>
                    </div>
                    <StatusPill status={LEVEL[f.level].status} label={LEVEL[f.level].label} />
                  </li>
                ))}
              </ul>
            )}
            {clear.length > 0 && (
              <div className="mt-3 flex flex-wrap items-center gap-1.5">
                <span className="inline-flex items-center gap-1 text-xs font-medium text-ink-2">
                  <CircleCheck className="h-3.5 w-3.5 text-status-good" aria-hidden />
                  All clear:
                </span>
                {clear.map((f) => (
                  <span key={f.key} title={f.reason} className="rounded-full bg-surface-2 px-2.5 py-1 text-xs text-ink-2">
                    {f.label}
                  </span>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </section>
  )
}
