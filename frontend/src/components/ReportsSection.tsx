import type { Conditions, SewerSpill, WaterIncident } from '../types'
import { ago, shortDate } from '../format'

function distance(mi: number | null): string | null {
  return mi != null ? `${mi} mi away` : null
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
    <div className="py-2 border-b border-surface-border last:border-0">
      <div className="text-sm text-slate-200">
        🚱 Sewage spill{gallons != null && ` · ${gallons.toLocaleString()} gal`}
        <span className={spill.reached_water ? 'text-red-300' : 'text-slate-500'}>
          {spill.reached_water ? ' · reached water' : ' · did not reach water'}
        </span>
      </div>
      <div className="text-xs text-slate-500">{meta.join(' · ')}</div>
      {spill.cause && <div className="text-xs text-slate-600">Cause: {spill.cause}</div>}
    </div>
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
    <div className="py-2 border-b border-surface-border last:border-0">
      <div className="text-sm text-slate-200">
        {incident.algal_bloom ? '🟢' : '🐟'} {incident.type}
        {incident.fish_count != null && (
          <span className="text-slate-400"> · ~{incident.fish_count.toLocaleString()} fish</span>
        )}
      </div>
      <div className="text-xs text-slate-500">{meta.join(' · ')}</div>
      {incident.location && <div className="text-xs text-slate-600">{incident.location}</div>}
      {incident.findings && (
        <details className="mt-1">
          <summary className="text-xs text-blue-400 cursor-pointer hover:text-blue-300">DEQ findings</summary>
          <p className="text-xs text-slate-400 mt-1 whitespace-pre-line">{incident.findings}</p>
        </details>
      )}
    </div>
  )
}

export function ReportsSection({ reports }: { reports: Conditions['reports'] }) {
  const spills = reports.sewer_spills ?? []
  const incidents = reports.incidents ?? []
  if (spills.length === 0 && incidents.length === 0) return null

  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-4">
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <span className="text-lg">📋</span>
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
            NC DEQ Reports Near River Bend
          </span>
        </div>
        <span className="text-xs text-slate-600">
          within {reports.radius_mi} mi · last {reports.lookback_days} days
        </span>
      </div>
      <div>
        {spills.map((s) => <SpillRow key={s.id} spill={s} />)}
        {incidents.map((i) => <IncidentRow key={i.id} incident={i} />)}
      </div>
    </div>
  )
}
