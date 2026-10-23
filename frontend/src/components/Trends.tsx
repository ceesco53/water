import { format, parseISO } from 'date-fns'
import { Table2, Target } from 'lucide-react'
import type { HistorySnapshot, TrackRecord } from '../types'
import { LineChart, type TrendPoint } from './LineChart'

const pct = (v: number) => (v > 0 && v < 0.01 ? '<1%' : `${Math.round(v * 100)}%`)

/** How the prediction has done: every Trent-side sample since logging began, next to that morning's chance. */
function TrackRecordPanel({ track }: { track: TrackRecord | null }) {
  if (!track || !track.since) return null
  const s = track.summary
  const since = format(parseISO(track.since), 'MMM d')
  return (
    <div className="mt-5 border-t border-line/10 pt-4">
      <div className="flex items-center gap-1.5 text-sm font-medium text-ink">
        <Target className="h-4 w-4 text-accent" aria-hidden />
        Track record
      </div>
      {!s ? (
        <p className="mt-1 text-xs text-ink-2">
          No Trent-side samples since logging began {since}. NC DEQ samples Union Point monthly in winter; Sound Rivers
          samples River Bend weekly from late May.
        </p>
      ) : (
        <>
          <p className="mt-1 text-xs leading-relaxed text-ink-2">
            Since {since}: {s.samples} Trent-side sample{s.samples === 1 ? '' : 's'}, {s.exceedances} over the standard.
            The prediction averaged {pct(s.mean_predicted)}; {pct(s.observed_rate)} actually exceeded.
            {s.exceedances > 0 && ` It flagged ${s.flagged_exceedances} of ${s.exceedances} ahead of time.`}
            {s.samples < 30 && ' Too few samples yet to judge accuracy — this fills in over time.'}
          </p>
          <details className="mt-2">
            <summary className="inline-flex cursor-pointer items-center gap-1.5 text-xs text-ink-2 hover:text-ink">
              <Table2 className="h-3.5 w-3.5" aria-hidden />
              Every sample
            </summary>
            <div className="mt-2 max-h-56 overflow-y-auto rounded-lg border border-line/10">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-surface-2 text-left text-ink-2">
                  <tr>
                    <th className="px-3 py-1.5 font-medium">Date</th>
                    <th className="px-3 py-1.5 font-medium">Site</th>
                    <th className="px-3 py-1.5 text-right font-medium">Predicted</th>
                    <th className="px-3 py-1.5 text-right font-medium">Result</th>
                  </tr>
                </thead>
                <tbody className="tabular-nums text-ink">
                  {[...track.samples].reverse().map((r) => (
                    <tr key={`${r.date}-${r.site}`} className="border-t border-line/5">
                      <td className="px-3 py-1">{format(parseISO(r.date), 'MMM d')}</td>
                      <td className="px-3 py-1">{r.site.split(',')[0]}</td>
                      <td className="px-3 py-1 text-right">{pct(r.predicted)}</td>
                      <td className="px-3 py-1 text-right">
                        {r.mpn != null ? `${r.mpn} MPN · ` : ''}
                        {r.exceeded ? 'over' : 'within'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      )}
    </div>
  )
}

/** The model's bacteria risk over the last week of logged refreshes, against its Caution line. */
export function Trends({ history, days, track }: { history: HistorySnapshot[]; days: number; track: TrackRecord | null }) {
  const risk: TrendPoint[] = history
    .filter((h) => h.risk_probability != null)
    .map((h) => ({ t: new Date(h.ts), v: h.risk_probability as number }))
  const line = [...history].reverse().find((h) => h.risk_caution_line != null)?.risk_caution_line ?? null
  // Room above both the data and the Caution line, in clean 10% steps
  const riskMax = Math.max(0.2, Math.ceil((Math.max(line ?? 0, ...risk.map((p) => p.v)) * 1.25) / 0.1) * 0.1)

  return (
    <section className="card p-5 sm:p-6" aria-labelledby="trends-title">
      <h2 id="trends-title" className="text-base font-semibold text-ink">
        Bacteria risk, last {days} days
      </h2>
      <p className="mt-0.5 text-xs text-ink-2">Predicted chance a sample would exceed the swim standard, every 30 minutes</p>

      <div className="mt-4">
        <LineChart
          points={risk}
          yMin={0}
          yMax={riskMax}
          formatValue={pct}
          label="Bacteria risk"
          references={line != null ? [{ value: line, label: `Caution ${(line * 100).toFixed(1)}%`, tone: 'warning' }] : []}
          plotHeight={170}
          emptyMessage="Building history — the trend fills in as readings are logged every 30 minutes."
        />
      </div>

      {risk.length >= 2 && (
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
                  <th className="px-3 py-1.5 text-right font-medium">Bacteria risk</th>
                </tr>
              </thead>
              <tbody className="tabular-nums text-ink">
                {[...risk].reverse().map((p) => (
                  <tr key={p.t.getTime()} className="border-t border-line/5">
                    <td className="px-3 py-1">{format(p.t, 'EEE MMM d, h:mm a')}</td>
                    <td className="px-3 py-1 text-right">{pct(p.v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}

      <TrackRecordPanel track={track} />
    </section>
  )
}
