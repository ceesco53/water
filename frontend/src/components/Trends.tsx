import type { HistorySnapshot } from '../types'
import { TrendChart, type TrendPoint } from './TrendChart'

const pct = (v: number) => (v > 0 && v < 0.01 ? '<1%' : `${Math.round(v * 100)}%`)

/** The last week of logged refreshes: swim score, and the model's bacteria risk vs its Caution line. */
export function Trends({ history, days }: { history: HistorySnapshot[]; days: number }) {
  const score: TrendPoint[] = history
    .filter((h) => h.score != null)
    .map((h) => ({ t: new Date(h.ts), v: h.score as number }))
  const risk: TrendPoint[] = history
    .filter((h) => h.risk_probability != null)
    .map((h) => ({ t: new Date(h.ts), v: h.risk_probability as number }))
  const line = [...history].reverse().find((h) => h.risk_caution_line != null)?.risk_caution_line ?? null

  // Room above both the data and the Caution line, in clean 10% steps
  const riskMax = Math.max(0.2, Math.ceil((Math.max(line ?? 0, ...risk.map((p) => p.v)) * 1.25) / 0.1) * 0.1)

  return (
    <div className="grid gap-4">
      <TrendChart
        title="Swim score"
        subtitle={`Every refresh, last ${days} days`}
        points={score}
        yMax={100}
        formatValue={(v) => `${Math.round(v)}`}
      />
      <TrendChart
        title="Predicted bacteria risk"
        subtitle="Chance a sample would exceed the swim standard"
        points={risk}
        yMax={riskMax}
        formatValue={pct}
        reference={line != null ? { value: line, label: `Caution ${(line * 100).toFixed(1)}%` } : undefined}
      />
    </div>
  )
}
