import { useCallback, useEffect, useRef, useState } from 'react'
import clsx from 'clsx'
import { formatDistanceToNow } from 'date-fns'
import { fetchConditions, forceRefresh } from './api'
import type { BacteriaReading, BacteriaRisk, Conditions, SewerSpill } from './types'
import { ago, shortDate } from './format'
import { ScoreCard } from './components/ScoreCard'
import { SignalCard } from './components/SignalCard'
import { GaugeSection } from './components/GaugeSection'
import { AlertsBanner } from './components/AlertsBanner'
import { BacteriaSites } from './components/BacteriaSites'
import { ReportsSection } from './components/ReportsSection'

const REFRESH_INTERVAL_MS = 10 * 60 * 1000 // 10 minutes

type StatusLevel = 'ok' | 'warn' | 'danger' | 'unknown'

// Mirror backend scoring.py: bacteria results count fully for a week, half
// for the second week, then not at all; reports count for 7d (fish kills,
// blooms) or 5d (sewage spills that reached water).
const BACTERIA_FULL_WEIGHT_DAYS = 7
const BACTERIA_HALF_WEIGHT_DAYS = 14
const INCIDENT_SCORE_DAYS = 7
const SPILL_SCORE_DAYS = 5

function bacteriaStatus(status: BacteriaReading['status']): StatusLevel {
  if (status === 'safe') return 'ok'
  if (status === 'caution') return 'warn'
  if (status === 'unsafe') return 'danger'
  return 'unknown'
}

function bacteriaLabel(status: BacteriaReading['status']): string {
  return { safe: 'Safe', caution: 'Caution', unsafe: 'Unsafe', unknown: 'Unknown' }[status]
}

function bacteriaDetail(r: BacteriaReading): string {
  if (r.source === 'Sound Rivers') return 'soundrivers.org · weekly pass/fail'
  return [r.advisory && `DEQ: ${r.advisory}`, r.geomean_mpn != null && `30-day geomean ${r.geomean_mpn}`]
    .filter(Boolean)
    .join(' · ')
}

function bacteriaNote(r: BacteriaReading): string {
  if (r.age_days != null && r.age_days > BACTERIA_HALF_WEIGHT_DAYS) {
    return 'Too old to count in the score — the risk model stands in'
  }
  if (r.age_days == null || r.age_days > BACTERIA_FULL_WEIGHT_DAYS) {
    return 'Over a week old — counts half in the score'
  }
  if (r.source === 'NC DEQ') return 'NC standard: one sample ≥104 or 30-day geomean ≥35 MPN/100mL'
  return 'Pass/fail weekly report — no numeric value from this source'
}

function rainStatus(inches: number | null): StatusLevel {
  if (inches == null) return 'unknown'
  if (inches > 1.0) return 'danger'
  if (inches > 0.25) return 'warn'
  return 'ok'
}

// Same thresholds the 72h factor uses in scoring.py
function rain72Status(inches: number | null): StatusLevel {
  if (inches == null) return 'unknown'
  if (inches > 2.0) return 'danger'
  if (inches > 1.0) return 'warn'
  return 'ok'
}

function windStatus(mph: number | null): StatusLevel {
  if (mph == null) return 'unknown'
  if (mph > 20) return 'warn'
  return 'ok'
}

function thunderStatus(pct: number | null): StatusLevel {
  if (pct == null) return 'unknown'
  if (pct >= 55) return 'danger'
  if (pct >= 25) return 'warn'
  return 'ok'
}

function vibrioStatus(level: Conditions['vibrio']['level']): StatusLevel {
  return ({ high: 'danger', elevated: 'warn', low: 'ok', unknown: 'unknown' } as const)[level]
}

function forecastStatus(w: Conditions['weather']): StatusLevel {
  if (w.qpf_72h_in != null) return rainStatus(w.qpf_72h_in)
  if (w.rain_forecast_pct == null) return 'unknown'
  return w.rain_forecast_pct >= 30 ? 'warn' : 'ok'
}

function memorialDay(year: number): Date {
  const d = new Date(Date.UTC(year, 4, 31)) // May 31
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7)) // back up to Monday
  return d
}

function laborDay(year: number): Date {
  const d = new Date(Date.UTC(year, 8, 1)) // Sep 1
  d.setUTCDate(d.getUTCDate() + ((8 - d.getUTCDay()) % 7)) // forward to Monday
  return d
}

function formatMonthDay(d: Date): string {
  return d.toLocaleDateString('en-US', { month: 'long', day: 'numeric', timeZone: 'UTC' })
}

// Sound Rivers samples 50+ Trent/Neuse sites weekly, Memorial Day through Labor
// Day. Derived from the federal holidays (rather than a hardcoded date) so this
// doesn't quietly go stale — a fixed "season starts May 22" string reads as a
// live outage once that date has passed, which it always eventually does.
function swimSeasonInfo(now: Date): { inSeason: boolean; label: string } {
  const year = now.getUTCFullYear()
  const start = memorialDay(year)
  const end = laborDay(year)
  if (now < start) {
    return { inSeason: false, label: `Season opens Memorial Day (${formatMonthDay(start)})` }
  }
  if (now > end) {
    return { inSeason: false, label: `Season ended Labor Day (${formatMonthDay(end)}) — resumes next Memorial Day` }
  }
  return { inSeason: true, label: `In season through Labor Day (${formatMonthDay(end)})` }
}

function BacteriaCard({ primary }: { primary: BacteriaReading | null }) {
  if (primary == null) {
    return (
      <SignalCard
        title="Bacteria"
        icon="🦠"
        status="unknown"
        primary="No data"
        secondary="No Sound Rivers or NC DEQ results available"
        detail="Check soundrivers.org/swim-guide or DEQ's advisory map"
        note="The predicted risk stands in until a sample comes in"
      />
    )
  }
  const stale = primary.age_days != null && primary.age_days > BACTERIA_HALF_WEIGHT_DAYS
  return (
    <SignalCard
      title={`Bacteria (${primary.source})`}
      icon="🦠"
      status={stale ? 'unknown' : bacteriaStatus(primary.status)}
      primary={primary.mpn != null ? `${primary.mpn} MPN/100mL` : bacteriaLabel(primary.status)}
      secondary={`${primary.site_name.split(',')[0]} · ${
        primary.sample_date ? `${shortDate(primary.sample_date)} (${ago(primary.age_days)})` : 'date unknown'
      }`}
      detail={bacteriaDetail(primary)}
      note={bacteriaNote(primary)}
    />
  )
}

function chance(p: number): string {
  return p < 0.01 ? '<1%' : `${Math.round(p * 100)}%`
}

function RiskCard({ risk }: { risk: BacteriaRisk | null }) {
  if (risk == null) {
    return <SignalCard title="Predicted Bacteria Risk" icon="📈" status="unknown" primary="Unavailable" detail="Risk model failed to load" />
  }
  const overLine = risk.probability >= risk.caution_probability
  const floorOnly = risk.summer_storm && !overLine
  return (
    <SignalCard
      title="Predicted Bacteria Risk"
      icon="📈"
      status={overLine || risk.summer_storm ? 'warn' : 'ok'}
      primary={chance(risk.probability)}
      secondary={
        floorOnly && risk.rain_72h_in != null
          ? `Big summer storm (${risk.rain_72h_in.toFixed(1)}" in 72h) — rated Caution`
          : 'Chance a sample today would exceed the swim standard'
      }
      detail={
        risk.missing_inputs.length > 0
          ? `${risk.missing_inputs.join(', ')} unavailable — held at its average`
          : `From rain, river flow & season · ${risk.trained.samples} DEQ samples ${risk.trained.years[0]}–${risk.trained.years[1]}`
      }
      note={`Caution at ≥${(risk.caution_probability * 100).toFixed(1)}%, or after ≥${risk.summer_floor_rain_in}" of rain in 72h May–Sep`}
    />
  )
}

function IncidentsCard({ reports }: { reports: Conditions['reports'] }) {
  const incidents = reports.incidents
  const scope = `NC DEQ · within ${reports.radius_mi} mi · last ${reports.lookback_days}d`
  if (incidents == null) {
    return <SignalCard title="Fish Kills & Blooms" icon="🐟" status="unknown" primary="Unavailable" detail="NC DEQ feed unreachable" />
  }
  const recentBloom = incidents.some((i) => i.algal_bloom && i.age_days <= INCIDENT_SCORE_DAYS)
  const latest = incidents[0]
  return (
    <SignalCard
      title="Fish Kills & Blooms"
      icon="🐟"
      status={recentBloom ? 'danger' : incidents.length > 0 ? 'warn' : 'ok'}
      primary={incidents.length > 0 ? `${incidents.length} report${incidents.length === 1 ? '' : 's'}` : 'None'}
      secondary={latest ? `Latest: ${latest.type} · ${shortDate(latest.date)}` : 'Nothing reported nearby'}
      detail={scope}
      note="Usually low-oxygen events; some blooms are toxic — avoid discolored water"
    />
  )
}

function SpillsCard({ reports }: { reports: Conditions['reports'] }) {
  const spills = reports.sewer_spills
  const scope = `NC DEQ · within ${reports.radius_mi} mi · last ${reports.lookback_days}d`
  if (spills == null) {
    return <SignalCard title="Sewage Spills" icon="🚱" status="unknown" primary="Unavailable" detail="NC DEQ feed unreachable" />
  }
  const gallons = (s: SewerSpill) => s.volume_reached_water_gal ?? s.volume_gal
  const reached = spills.filter((s) => s.reached_water)
  const scored = reached.some((s) => s.ongoing || s.age_days <= SPILL_SCORE_DAYS)
  const worst = reached.length > 0
    ? reached.reduce((a, b) => ((gallons(b) ?? 0) > (gallons(a) ?? 0) ? b : a))
    : null
  const worstGallons = worst ? gallons(worst) : null
  return (
    <SignalCard
      title="Sewage Spills"
      icon="🚱"
      status={scored ? 'danger' : reached.length > 0 ? 'warn' : 'ok'}
      primary={reached.length > 0 ? `${reached.length} reached water` : spills.length > 0 ? 'None reached water' : 'None'}
      secondary={
        worst
          ? `${worstGallons != null ? `${worstGallons.toLocaleString()} gal · ` : ''}${worst.waterbody ?? 'surface water'} · ${shortDate(worst.date)}`
          : spills.length > 0
          ? `${spills.length} spill${spills.length === 1 ? '' : 's'} contained on land`
          : 'Nothing reported nearby'
      }
      detail={scope}
      note="Sewage reaching the river is a direct bacteria source"
    />
  )
}

export default function App() {
  const [data, setData] = useState<Conditions | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const season = swimSeasonInfo(new Date())

  const load = useCallback(async () => {
    try {
      const result = await fetchConditions()
      setData(result)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load conditions')
    } finally {
      setLoading(false)
    }
  }, [])

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      const result = await forceRefresh()
      setData(result)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Refresh failed')
    } finally {
      setRefreshing(false)
    }
  }

  useEffect(() => {
    load()
    intervalRef.current = setInterval(load, REFRESH_INTERVAL_MS)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [load])

  return (
    <div className="min-h-screen bg-surface">
      {/* Header */}
      <header className="border-b border-surface-border bg-surface-card/50 backdrop-blur sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-slate-100 flex items-center gap-2">
              <span>🌊</span> River Bend Water Monitor
            </h1>
            <p className="text-xs text-slate-500">Trent River · New Bern, NC</p>
          </div>
          <div className="flex items-center gap-3">
            {data && (
              <span className="text-xs text-slate-500 hidden sm:block">
                Updated {formatDistanceToNow(new Date(data.last_updated), { addSuffix: true })}
                {data.cache_age_seconds > 0 && (
                  <span className="text-slate-600"> · cached</span>
                )}
              </span>
            )}
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className={clsx(
                'text-xs px-3 py-1.5 rounded-lg border border-surface-border',
                'text-slate-400 hover:text-slate-200 hover:border-slate-500 transition-colors',
                refreshing && 'opacity-50 cursor-not-allowed'
              )}
            >
              {refreshing ? 'Refreshing…' : '↺ Refresh'}
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-6 space-y-6">
        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center h-64">
            <div className="text-slate-500 text-sm animate-pulse">Loading conditions…</div>
          </div>
        )}

        {/* Error */}
        {error && !loading && (
          <div className="rounded-xl border border-red-500/40 bg-red-900/10 p-4 text-red-300 text-sm">
            {error}
          </div>
        )}

        {data && (
          <>
            {/* Active NWS alerts */}
            {data.alerts && <AlertsBanner alerts={data.alerts} />}

            {/* Score card */}
            <ScoreCard
              score={data.score}
              rating={data.rating}
              color={data.rating_color}
              factors={data.score_factors}
            />

            {/* Signal grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <BacteriaCard primary={data.bacteria.primary} />
              <RiskCard risk={data.bacteria_risk} />

              {/* Rainfall 24h */}
              <SignalCard
                title="Rainfall — Last 24h"
                icon="🌧️"
                status={data.weather.rain_gauge_issue ? 'unknown' : rainStatus(data.weather.rain_24h_in)}
                primary={
                  data.weather.rain_24h_in != null
                    ? `${data.weather.rain_24h_in.toFixed(2)}"`
                    : 'No data'
                }
                secondary={
                  data.weather.rain_gauge_issue
                    ? 'Gauge unreliable — may be undercounted'
                    : data.weather.rain_24h_in != null && data.weather.rain_24h_in > 1.0
                    ? 'Heavy — runoff risk'
                    : data.weather.rain_24h_in != null && data.weather.rain_24h_in > 0.25
                    ? 'Moderate rain'
                    : 'Light / dry'
                }
                detail="KEWN (Craven County Airport)"
                note={data.weather.rain_gauge_issue ?? undefined}
              />

              {/* Rainfall 72h */}
              <SignalCard
                title="Rainfall — Last 72h"
                icon="⛈️"
                status={data.weather.rain_gauge_issue ? 'unknown' : rain72Status(data.weather.rain_72h_in)}
                primary={
                  data.weather.rain_72h_in != null
                    ? `${data.weather.rain_72h_in.toFixed(2)}"`
                    : 'No data'
                }
                secondary={
                  data.weather.rain_gauge_issue
                    ? 'Gauge unreliable — may be undercounted'
                    : data.weather.rain_72h_in != null && data.weather.rain_72h_in > 2.0
                    ? 'Peak contamination window'
                    : data.weather.rain_72h_in != null && data.weather.rain_72h_in > 1.0
                    ? 'Elevated 72h accumulation'
                    : 'Dry period — low risk'
                }
                detail={data.weather.rain_7d_in != null ? `Last 7 days: ${data.weather.rain_7d_in.toFixed(2)}"` : undefined}
                note="48–72h post-rain = peak risk in eastern NC"
              />

              {/* Rain forecast — expected amount, not just chance */}
              <SignalCard
                title="Rain Forecast (72h)"
                icon="📅"
                status={forecastStatus(data.weather)}
                primary={
                  data.weather.qpf_72h_in != null
                    ? `${data.weather.qpf_72h_in.toFixed(2)}" expected`
                    : data.weather.rain_forecast_pct != null
                    ? `${data.weather.rain_forecast_pct}% chance`
                    : 'No forecast'
                }
                secondary={
                  data.weather.qpf_72h_in != null && data.weather.qpf_72h_in >= 0.25
                    ? 'Bacteria risk rises 48–72h after'
                    : data.weather.rain_forecast_pct != null
                    ? `Peak chance ${data.weather.rain_forecast_pct}% · ${data.weather.rain_forecast_period}`
                    : 'No rain in the forecast'
                }
                detail="NWS · River Bend grid cell"
                note="Plan swims before rain or 3+ days after"
              />

              {/* Lightning */}
              <SignalCard
                title="Lightning Risk"
                icon="⚡"
                status={thunderStatus(data.weather.thunder_pct_6h)}
                primary={data.weather.thunder_pct_6h != null ? `${data.weather.thunder_pct_6h}%` : 'No data'}
                secondary="Chance of thunder, next 6h"
                detail={data.weather.thunder_pct_24h != null ? `Next 24h: ${data.weather.thunder_pct_24h}%` : undefined}
                note="Hear thunder? Get out of the water"
              />

              {/* Water temp */}
              <SignalCard
                title="Water Temperature"
                icon="🌡️"
                status={
                  data.water.temp_f == null
                    ? 'unknown'
                    : data.water.temp_f < 60
                    ? 'warn'
                    : 'ok'
                }
                primary={data.water.temp_f != null ? `${data.water.temp_f}°F` : 'No data'}
                secondary={
                  data.water.temp_f != null
                    ? data.water.temp_f >= 75
                      ? 'Warm — comfortable'
                      : data.water.temp_f >= 65
                      ? 'Moderate'
                      : 'Cool'
                    : 'No sensor reachable'
                }
                detail={
                  data.water.temp_source
                    ? `${data.water.temp_source}${data.water.temp_date ? ` · ${shortDate(data.water.temp_date)}` : ''}`
                    : undefined
                }
                note={
                  data.water.temp_date
                    ? 'Measured on site when DEQ sampled'
                    : 'Ocean-inlet proxy ~40 mi SE — the shallow Trent runs warmer in summer, cooler in winter'
                }
              />

              {/* Vibrio */}
              <SignalCard
                title="Vibrio Risk"
                icon="🧫"
                status={vibrioStatus(data.vibrio.level)}
                primary={data.vibrio.level.charAt(0).toUpperCase() + data.vibrio.level.slice(1)}
                secondary={data.vibrio.reason}
                detail={
                  data.water.salinity_ppt != null && data.water.salinity_site && data.water.salinity_date
                    ? `Salinity at ${data.water.salinity_site.split(',')[0]} · ${shortDate(data.water.salinity_date)}`
                    : undefined
                }
                note="For open wounds, liver disease or weak immunity — not in score"
              />

              <IncidentsCard reports={data.reports} />
              <SpillsCard reports={data.reports} />

              {/* Wind */}
              <SignalCard
                title="Wind"
                icon="💨"
                status={windStatus(data.weather.wind_speed_mph)}
                primary={
                  data.weather.wind_speed_mph != null
                    ? `${data.weather.wind_speed_mph.toFixed(0)} mph`
                    : 'No data'
                }
                secondary={
                  data.weather.wind_direction
                    ? `From ${data.weather.wind_direction}`
                    : undefined
                }
                detail="NOAA surface observation"
                note="Estuarine mixing near Neuse confluence"
              />

              {/* Upstream flow summary */}
              <SignalCard
                title="Upstream Discharge"
                icon="🏞️"
                status={
                  data.gauges.upstream.discharge_cfs != null &&
                  data.gauges.upstream.discharge_p80 != null &&
                  data.gauges.upstream.discharge_cfs > data.gauges.upstream.discharge_p80
                    ? 'warn'
                    : data.gauges.upstream.discharge_cfs != null
                    ? 'ok'
                    : 'unknown'
                }
                primary={
                  data.gauges.upstream.discharge_cfs != null
                    ? `${data.gauges.upstream.discharge_cfs.toFixed(0)} ft³/s`
                    : 'No data'
                }
                secondary={
                  data.gauges.upstream.discharge_p80 != null
                    ? `80th pct for today: ${data.gauges.upstream.discharge_p80.toFixed(0)} ft³/s`
                    : undefined
                }
                detail="Trent near Trenton — runoff indicator"
              />
            </div>

            <BacteriaSites
              readings={data.bacteria.readings}
              primary={data.bacteria.primary}
              seasonLabel={season.label}
            />

            <ReportsSection reports={data.reports} />

            {/* USGS Gauge Detail Table */}
            <GaugeSection
              upstream={data.gauges.upstream}
              local={data.gauges.local}
            />
          </>
        )}
      </main>

      {/* Footer */}
      <footer className="max-w-5xl mx-auto px-4 py-6 mt-4 border-t border-surface-border">
        <p className="text-xs text-slate-600 text-center">
          Data from{' '}
          <a
            href="https://waterdata.usgs.gov/"
            className="text-slate-500 hover:text-slate-300 underline"
            target="_blank"
            rel="noreferrer"
          >
            USGS
          </a>
          {' · '}
          <a
            href="https://soundrivers.org/swim-guide/"
            className="text-slate-500 hover:text-slate-300 underline"
            target="_blank"
            rel="noreferrer"
          >
            Sound Rivers
          </a>
          {' · '}
          <a
            href="https://ncdenr.maps.arcgis.com/apps/dashboards/99430d6fd1824b78ae328c6a5538852f"
            className="text-slate-500 hover:text-slate-300 underline"
            target="_blank"
            rel="noreferrer"
          >
            NC DEQ
          </a>
          {' · '}
          <a
            href="https://api.weather.gov/"
            className="text-slate-500 hover:text-slate-300 underline"
            target="_blank"
            rel="noreferrer"
          >
            NOAA
          </a>
          {' · '}
          Auto-refreshes every 10 minutes
        </p>
      </footer>
    </div>
  )
}
