import { Biohazard, ChevronDown, Fish, Sprout } from 'lucide-react'
import type { Conditions, SewerSpill, WaterIncident } from '../types'
import { ago, shortDate } from '../format'

function distance(mi: number | null): string | null {
  return mi != null ? `${mi} mi away` : null
}

function Row({ icon: Icon, title, meta, extra }: {
  icon: typeof Fish
  title: React.ReactNode
  meta: string
  extra?: React.ReactNode
}) {
  return (
    <li className="flex gap-3 py-3">
      <span className="mt-0.5 grid h-7 w-7 flex-shrink-0 place-items-center rounded-lg bg-surface-2">
        <Icon className="h-4 w-4 text-ink-2" aria-hidden />
      </span>
      <div className="min-w-0">
        <div className="text-sm font-medium text-ink">{title}</div>
        <div className="text-xs text-ink-2">{meta}</div>
        {extra}
      </div>
    </li>
  )
}

function SpillRow({ spill }: { spill: SewerSpill }) {
  const gallons = spill.volume_reached_water_gal ?? spill.volume_gal
  const meta = [
    spill.system,
    spill.waterbody ?? spill.location,
    distance(spill.distance_mi),
    spill.ongoing ? 'ongoing' : `${shortDate(spill.date)} (${ago(spill.age_days)})`,
  ].filter(Boolean)
  return (
    <Row
      icon={Biohazard}
      title={
        <>
          Sewage spill{gallons != null && ` · ${gallons.toLocaleString()} gal`}
          <span className="font-normal text-ink-2">{spill.reached_water ? ' · reached the water' : ' · stayed on land'}</span>
        </>
      }
      meta={meta.join(' · ')}
      extra={spill.cause && <div className="text-xs text-muted">Cause: {spill.cause}</div>}
    />
  )
}

function IncidentRow({ incident }: { incident: WaterIncident }) {
  const meta = [
    incident.waterbody,
    distance(incident.distance_mi),
    `${shortDate(incident.date)} (${ago(incident.age_days)})`,
    incident.investigation_status && `DEQ: ${incident.investigation_status.toLowerCase()}`,
  ].filter(Boolean)
  return (
    <Row
      icon={incident.algal_bloom ? Sprout : Fish}
      title={
        <>
          {incident.type}
          {incident.fish_count != null && (
            <span className="font-normal text-ink-2"> · ~{incident.fish_count.toLocaleString()} fish</span>
          )}
        </>
      }
      meta={meta.join(' · ')}
      extra={
        <>
          {incident.location && <div className="mt-0.5 text-xs text-muted">{incident.location}</div>}
          {incident.findings && (
            <details className="group mt-1">
              <summary className="inline-flex cursor-pointer items-center gap-1 text-xs font-medium text-accent">
                DEQ findings
                <ChevronDown className="h-3 w-3 transition group-open:rotate-180" aria-hidden />
              </summary>
              <p className="mt-1 whitespace-pre-line text-xs text-ink-2">{incident.findings}</p>
            </details>
          )}
        </>
      }
    />
  )
}

export function ReportsSection({ reports }: { reports: Conditions['reports'] }) {
  const spills = reports.sewer_spills ?? []
  const incidents = reports.incidents ?? []
  if (spills.length === 0 && incidents.length === 0) return null

  return (
    <section className="card p-5 sm:p-6" aria-labelledby="reports-title">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="reports-title" className="text-base font-semibold text-ink">
          NC DEQ reports nearby
        </h2>
        <span className="text-xs text-muted">
          Within {reports.radius_mi} mi · last {reports.lookback_days} days
        </span>
      </div>
      <ul className="mt-2 divide-y divide-line/[0.06]">
        {spills.map((s) => <SpillRow key={s.id} spill={s} />)}
        {incidents.map((i) => <IncidentRow key={i.id} incident={i} />)}
      </ul>
    </section>
  )
}
