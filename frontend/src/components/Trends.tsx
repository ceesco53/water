import { useState } from 'react'
import clsx from 'clsx'
import { format } from 'date-fns'
import { Table2 } from 'lucide-react'
import type { HistorySnapshot } from '../types'
import { LineChart, type Reference, type TrendPoint } from './LineChart'

const pct = (v: number) => (v > 0 && v < 0.01 ? '<1%' : `${Math.round(v * 100)}%`)

type View = 'score' | 'risk'

/**
 * The last week of logged refreshes in one card: swim score, or the model's
 * bacteria risk against its Caution line, switched with a segmented control.
 */
export function Trends({ history, days }: { history: HistorySnapshot[]; days: number }) {
  const [view, setView] = useState<View>('score')

  const score: TrendPoint[] = history
    .filter((h) => h.score != null)
    .map((h) => ({ t: new Date(h.ts), v: h.score as number }))
  const risk: TrendPoint[] = history
    .filter((h) => h.risk_probability != null)
    .map((h) => ({ t: new Date(h.ts), v: h.risk_probability as number }))
  const line = [...history].reverse().find((h) => h.risk_caution_line != null)?.risk_caution_line ?? null
  // Room above both the data and the Caution line, in clean 10% steps
  const riskMax = Math.max(0.2, Math.ceil((Math.max(line ?? 0, ...risk.map((p) => p.v)) * 1.25) / 0.1) * 0.1)

  const series = {
    score: {
      tab: 'Swim score',
      subtitle: 'The overall score at every refresh',
      points: score,
      yMax: 100,
      format: (v: number) => `${Math.round(v)}`,
      refs: [] as Reference[],
    },
    risk: {
      tab: 'Bacteria risk',
      subtitle: 'Predicted chance a sample would exceed the swim standard',
      points: risk,
      yMax: riskMax,
      format: pct,
      refs: line != null ? [{ value: line, label: `Caution ${(line * 100).toFixed(1)}%`, tone: 'warning' as const }] : [],
    },
  }[view]

  return (
    <section className="card p-5 sm:p-6" aria-labelledby="trends-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="trends-title" className="text-base font-semibold text-ink">
            Last {days} days
          </h2>
          <p className="mt-0.5 text-xs text-ink-2">{series.subtitle}</p>
        </div>
        <div className="inline-flex rounded-full bg-surface-2 p-0.5" role="tablist" aria-label="Trend to show">
          {(['score', 'risk'] as View[]).map((v) => (
            <button
              key={v}
              type="button"
              role="tab"
              aria-selected={view === v}
              onClick={() => setView(v)}
              className={clsx(
                'rounded-full px-3 py-1 text-xs font-medium transition',
                view === v ? 'bg-surface text-ink shadow-sm' : 'text-ink-2 hover:text-ink'
              )}
            >
              {v === 'score' ? 'Swim score' : 'Bacteria risk'}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-4" role="tabpanel">
        <LineChart
          points={series.points}
          yMin={0}
          yMax={series.yMax}
          formatValue={series.format}
          label={series.tab}
          references={series.refs}
          plotHeight={190}
          emptyMessage="Building history — the trend fills in as readings are logged every 30 minutes."
        />
      </div>

      {series.points.length >= 2 && (
        <details className="mt-3">
          <summary className="inline-flex cursor-pointer items-center gap-1.5 text-xs text-ink-2 hover:text-ink">
            <Table2 className="h-3.5 w-3.5" aria-hidden />
            View as table
          </summary>
          <div className="mt-2 max-h-56 overflow-y-auto rounded-lg border border-line/10">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-surface-2 text-left text-ink-2">
                <tr>
                  <th className="px-3 py-1.5 font-medium">Time</th>
                  <th className="px-3 py-1.5 text-right font-medium">{series.tab}</th>
                </tr>
              </thead>
              <tbody className="tabular-nums text-ink">
                {[...series.points].reverse().map((p) => (
                  <tr key={p.t.getTime()} className="border-t border-line/5">
                    <td className="px-3 py-1">{format(p.t, 'EEE MMM d, h:mm a')}</td>
                    <td className="px-3 py-1 text-right">{series.format(p.v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </section>
  )
}
