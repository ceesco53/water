import clsx from 'clsx'
import { CircleCheck } from 'lucide-react'
import type { ScoreFactor } from '../types'

// The largest single deduction the score can take (an unsafe fresh sample)
const MAX_DEDUCTION = 60

function severity(impact: number): { bar: string; label: string } {
  if (impact <= -30) return { bar: 'bg-status-critical', label: 'Major' }
  if (impact <= -15) return { bar: 'bg-status-serious', label: 'Moderate' }
  return { bar: 'bg-status-warning', label: 'Minor' }
}

const minus = (n: number) => `−${Math.abs(n)}`

/**
 * Today's score, explained: each factor that costs points gets its reason and
 * a bar for the cost; everything else folds into one quiet "no effect" line.
 */
export function FactorBreakdown({ score, factors }: { score: number; factors: ScoreFactor[] }) {
  const costing = factors.filter((f) => f.impact < 0).sort((a, b) => a.impact - b.impact)
  const clear = factors.filter((f) => f.impact >= 0)

  return (
    <section className="card p-5 sm:p-6" aria-labelledby="factors-title">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="factors-title" className="text-base font-semibold text-ink">
          What's shaping today's score
        </h2>
        <span className="text-sm text-muted">
          100 {costing.length > 0 && minus(100 - score)} = <span className="font-semibold text-ink">{score}</span>
        </span>
      </div>

      {costing.length === 0 ? (
        <p className="mt-5 text-sm text-ink-2">Nothing is costing points today.</p>
      ) : (
        <ul className="mt-5 space-y-4">
          {costing.map((f) => {
            const sev = severity(f.impact)
            return (
              <li key={f.label} className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1.5">
                <div className="min-w-0">
                  <div className="text-sm font-medium text-ink">{f.label}</div>
                  <p className="text-xs leading-relaxed text-ink-2">{f.reason}</p>
                </div>
                <div className="pt-0.5 text-sm font-semibold text-ink">
                  {minus(f.impact)}
                  <span className="sr-only"> points, {sev.label.toLowerCase()} effect</span>
                </div>
                <div className="col-span-2 h-1.5 rounded-full bg-surface-2" aria-hidden>
                  <div
                    className={clsx('h-full rounded-full', sev.bar)}
                    style={{ width: `${Math.min(100, (Math.abs(f.impact) / MAX_DEDUCTION) * 100)}%` }}
                  />
                </div>
              </li>
            )
          })}
        </ul>
      )}

      {clear.length > 0 && (
        <div className="mt-5 border-t border-line/10 pt-4">
          <div className="flex items-center gap-1.5 text-xs font-medium text-ink-2">
            <CircleCheck className="h-3.5 w-3.5 text-status-good" aria-hidden />
            No effect today
          </div>
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {clear.map((f) => (
              <li key={f.label} title={f.reason} className="rounded-full bg-surface-2 px-2.5 py-1 text-xs text-ink-2">
                {f.label}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
