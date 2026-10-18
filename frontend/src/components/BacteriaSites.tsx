import clsx from 'clsx'
import { ChevronDown, MapPin } from 'lucide-react'
import type { BacteriaReading } from '../types'
import type { StatusLevel } from '../status'
import { ago, shortDate } from '../format'
import { StatusPill } from './StatusPill'

interface Props {
  readings: BacteriaReading[]
  primary: BacteriaReading | null
  seasonLabel: string
}

// Mirrors BACTERIA_HALF_WEIGHT_DAYS in backend scoring.py
const STALE_DAYS = 14

const STATUS_OF: Record<BacteriaReading['status'], { level: StatusLevel; label: string }> = {
  safe: { level: 'ok', label: 'Safe' },
  caution: { level: 'warn', label: 'Caution' },
  unsafe: { level: 'danger', label: 'Unsafe' },
  unknown: { level: 'unknown', label: 'Not tested' },
}

const REACH_LABEL: Record<BacteriaReading['reach'], string> = {
  home: 'Your stretch',
  trent: 'Trent River',
  neuse: 'Neuse · not scored',
}

function readingDetail(r: BacteriaReading): string {
  const parts: string[] = [r.source]
  if (r.distance_mi != null) parts.push(`${r.distance_mi} mi`)
  parts.push(r.sample_date ? `${shortDate(r.sample_date)} (${ago(r.age_days)})` : 'date unknown')
  if (r.mpn != null) parts.push(`${r.mpn} MPN`)
  if (r.geomean_mpn != null) parts.push(`30-day geomean ${r.geomean_mpn}`)
  if (r.advisory && r.advisory !== 'No Advisory') parts.push(`DEQ: ${r.advisory}`)
  return parts.join(' · ')
}

function SiteRow({ r, primary }: { r: BacteriaReading; primary: BacteriaReading | null }) {
  const isPrimary = primary != null && r.source === primary.source && r.site_id === primary.site_id
  const faded = (r.age_days != null && r.age_days > STALE_DAYS) || r.reach === 'neuse'
  const s = STATUS_OF[r.status]
  return (
    <li
      className={clsx(
        'flex items-center justify-between gap-3 py-3',
        faded && !isPrimary && 'opacity-55',
        isPrimary && '-mx-3 rounded-xl bg-accent/[0.07] px-3'
      )}
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
          <span className={clsx('text-sm text-ink', isPrimary ? 'font-semibold' : 'font-medium')}>{r.site_name}</span>
          <span className="text-xs text-muted">{REACH_LABEL[r.reach]}</span>
          {isPrimary && (
            <span className="rounded-full bg-accent px-2 py-0.5 text-[11px] font-medium text-white">Drives score</span>
          )}
        </div>
        <div className="mt-0.5 text-xs text-ink-2">{readingDetail(r)}</div>
      </div>
      <StatusPill status={s.level} label={s.label} />
    </li>
  )
}

export function BacteriaSites({ readings, primary, seasonLabel }: Props) {
  if (readings.length === 0) return null
  // Trent-side sites can drive the score; Neuse sites are context, folded away
  const scored = readings.filter((r) => r.reach !== 'neuse')
  const neuse = readings.filter((r) => r.reach === 'neuse')

  return (
    <section className="card p-5 sm:p-6" aria-labelledby="sites-title">
      <div className="flex items-center gap-2">
        <MapPin className="h-4 w-4 text-accent" aria-hidden />
        <h2 id="sites-title" className="text-base font-semibold text-ink">
          Bacteria sampling sites
        </h2>
      </div>

      <ul className="mt-4 divide-y divide-line/[0.06]">
        {scored.map((r) => (
          <SiteRow key={`${r.source}-${r.site_id}`} r={r} primary={primary} />
        ))}
      </ul>

      {neuse.length > 0 && (
        <details className="group mt-1">
          <summary className="inline-flex cursor-pointer items-center gap-1 py-2 text-xs font-medium text-accent">
            {neuse.length} Neuse River site{neuse.length === 1 ? '' : 's'} (not scored)
            <ChevronDown className="h-3.5 w-3.5 transition group-open:rotate-180" aria-hidden />
          </summary>
          <ul className="divide-y divide-line/[0.06]">
            {neuse.map((r) => (
              <SiteRow key={`${r.source}-${r.site_id}`} r={r} primary={primary} />
            ))}
          </ul>
        </details>
      )}

      <div className="mt-4 space-y-1.5 border-t border-line/10 pt-4 text-xs text-ink-2">
        <p>
          The score uses the freshest results from the closest water: River Bend's shoreline first, then the rest of the
          Trent, taking the worst result from the last 7 days. Faded rows are more than {STALE_DAYS} days old.
        </p>
        <p>
          <a href="https://soundrivers.org/swim-guide/" target="_blank" rel="noreferrer" className="font-medium text-accent hover:underline">
            Sound Rivers
          </a>{' '}
          samples weekly in summer. {seasonLabel}.{' '}
          <a
            href="https://ncdenr.maps.arcgis.com/apps/dashboards/99430d6fd1824b78ae328c6a5538852f"
            target="_blank"
            rel="noreferrer"
            className="font-medium text-accent hover:underline"
          >
            NC DEQ
          </a>{' '}
          samples weekly to biweekly April–October and monthly November–March.
        </p>
      </div>
    </section>
  )
}
