import clsx from 'clsx'
import type { BacteriaReading } from '../types'
import { ago, shortDate } from '../format'

interface Props {
  readings: BacteriaReading[]
  primary: BacteriaReading | null
  seasonLabel: string
}

// Mirrors BACTERIA_HALF_WEIGHT_DAYS in backend scoring.py
const STALE_DAYS = 14

const badgeClass: Record<BacteriaReading['status'], string> = {
  safe: 'bg-green-500/20 text-green-300 border-green-500/30',
  caution: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30',
  unsafe: 'bg-red-500/20 text-red-300 border-red-500/30',
  unknown: 'bg-slate-700 text-slate-400 border-slate-600',
}

function readingDetail(r: BacteriaReading): string {
  const parts: string[] = [r.source]
  parts.push(r.sample_date ? `${shortDate(r.sample_date)} (${ago(r.age_days)})` : 'date unknown')
  if (r.mpn != null) parts.push(`${r.mpn} MPN`)
  if (r.geomean_mpn != null) parts.push(`30d geomean ${r.geomean_mpn}`)
  if (r.advisory && r.advisory !== 'No Advisory') parts.push(`DEQ: ${r.advisory}`)
  return parts.join(' · ')
}

export function BacteriaSites({ readings, primary, seasonLabel }: Props) {
  if (readings.length === 0) return null

  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-lg">📍</span>
        <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
          Bacteria Sampling Sites
        </span>
      </div>
      <div>
        {readings.map((r) => {
          const isPrimary = primary != null && r.source === primary.source && r.site_id === primary.site_id
          const stale = r.age_days != null && r.age_days > STALE_DAYS
          return (
            <div
              key={`${r.source}-${r.site_id}`}
              className={clsx(
                'flex items-center justify-between gap-3 py-2 border-b border-surface-border last:border-0',
                stale && 'opacity-50'
              )}
            >
              <div className="min-w-0">
                <div className={clsx('text-sm', isPrimary ? 'text-slate-100 font-semibold' : 'text-slate-300')}>
                  {r.site_name}
                  {isPrimary && <span className="ml-2 text-xs font-normal text-blue-400">drives score</span>}
                </div>
                <div className="text-xs text-slate-500">{readingDetail(r)}</div>
              </div>
              <span className={clsx('text-xs px-2 py-0.5 rounded-full font-medium border flex-shrink-0', badgeClass[r.status])}>
                {r.status.charAt(0).toUpperCase() + r.status.slice(1)}
              </span>
            </div>
          )
        })}
      </div>
      <div className="mt-3 text-xs text-slate-600 space-y-1">
        <p>
          Score uses the worst result sampled in the last 7 days; with none that recent, the newest
          result at reduced weight. Faded rows are over {STALE_DAYS} days old.
        </p>
        <p>
          <a href="https://soundrivers.org/swim-guide/" target="_blank" rel="noreferrer" className="underline hover:text-slate-400">
            Sound Rivers
          </a>
          : weekly in summer. {seasonLabel}.{' '}
          <a
            href="https://ncdenr.maps.arcgis.com/apps/dashboards/99430d6fd1824b78ae328c6a5538852f"
            target="_blank"
            rel="noreferrer"
            className="underline hover:text-slate-400"
          >
            NC DEQ
          </a>
          : weekly–biweekly Apr–Oct, monthly Nov–Mar.
        </p>
      </div>
    </div>
  )
}
