import { useCallback, useEffect, useState, type ReactNode } from 'react'
import {
  Activity,
  Biohazard,
  CalendarClock,
  CloudDrizzle,
  CloudRain,
  Fish,
  FlaskConical,
  Microscope,
  ShieldAlert,
  Thermometer,
  Wind,
  Zap,
  type LucideIcon,
} from 'lucide-react'
import { fetchConditions, fetchHistory, forceRefresh } from './api'
import type { BacteriaReading, BacteriaRisk, Conditions, HistorySnapshot, SewerSpill } from './types'
import type { StatusLevel } from './status'
import { ago, shortDate } from './format'
import { Hero } from './components/Hero'
import { FactorBreakdown } from './components/FactorBreakdown'
import { Trends } from './components/Trends'
import { SignalCard } from './components/SignalCard'
import { Meter } from './components/Meter'
import { GaugeSection } from './components/GaugeSection'
import { AlertsBanner } from './components/AlertsBanner'
import { BacteriaSites } from './components/BacteriaSites'
import { ReportsSection } from './components/ReportsSection'

const REFRESH_INTERVAL_MS = 10 * 60 * 1000 // 10 minutes
const HISTORY_DAYS = 7

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

// Same thresholds the 72h factor used in scoring.py
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
    return { inSeason: false, label: `Season ended Labor Day (${formatMonthDay(end)}) and resumes next Memorial Day` }
  }
  return { inSeason: true, label: `In season through Labor Day (${formatMonthDay(end)})` }
}

function chance(p: number): string {
  return p < 0.01 ? '<1%' : `${Math.round(p * 100)}%`
}

function Section({ icon: Icon, title, subtitle, children }: {
  icon: LucideIcon
  title: string
  subtitle: string
  children: ReactNode
}) {
  const id = `section-${title.toLowerCase().replace(/\W+/g, '-')}`
  return (
    <section aria-labelledby={id} className="space-y-4">
      <div className="flex items-end gap-3">
        <span className="grid h-9 w-9 place-items-center rounded-xl bg-accent text-white shadow-sm">
          <Icon className="h-[18px] w-[18px]" aria-hidden />
        </span>
        <div>
          <h2 id={id} className="text-xl font-semibold tracking-tight text-ink">
            {title}
          </h2>
          <p className="text-sm text-ink-2">{subtitle}</p>
        </div>
      </div>
      {children}
    </section>
  )
}

function BacteriaCard({ primary }: { primary: BacteriaReading | null }) {
  if (primary == null) {
    return (
      <SignalCard
        title="Latest bacteria sample"
        icon={Microscope}
        status="unknown"
        value="No sample"
        caption="No recent Sound Rivers or NC DEQ result on the Trent"
        note="The predicted risk stands in until a sample comes in"
      />
    )
  }
  const stale = primary.age_days != null && primary.age_days > BACTERIA_HALF_WEIGHT_DAYS
  return (
    <SignalCard
      title="Latest bacteria sample"
      icon={Microscope}
      status={stale ? 'unknown' : bacteriaStatus(primary.status)}
      statusLabel={stale ? 'Too old' : bacteriaLabel(primary.status)}
      value={primary.mpn != null ? `${primary.mpn} MPN` : bacteriaLabel(primary.status)}
      caption={`${primary.site_name.split(',')[0]} · ${
        primary.sample_date ? `${shortDate(primary.sample_date)} (${ago(primary.age_days)})` : 'date unknown'
      }`}
      detail={bacteriaDetail(primary)}
      note={bacteriaNote(primary)}
    />
  )
}

function RiskCard({ risk }: { risk: BacteriaRisk | null }) {
  if (risk == null) {
    return <SignalCard title="Predicted bacteria risk" icon={FlaskConical} status="unknown" value="Unavailable" caption="Risk model failed to load" />
  }
  const overLine = risk.probability >= risk.caution_probability
  const floorOnly = risk.summer_storm && !overLine
  const scaleMax = Math.max(risk.caution_probability * 2, Math.ceil(risk.probability * 10) / 10)
  return (
    <SignalCard
      title="Predicted bacteria risk"
      icon={FlaskConical}
      status={overLine || risk.summer_storm ? 'warn' : 'ok'}
      statusLabel={overLine || risk.summer_storm ? 'Caution' : 'Low'}
      value={chance(risk.probability)}
      caption={
        floorOnly && risk.rain_72h_in != null
          ? `Big summer storm (${risk.rain_72h_in.toFixed(1)}" in 72h) — rated Caution`
          : 'Chance a sample today would exceed the swim standard'
      }
      detail={
        risk.missing_inputs.length > 0
          ? `${risk.missing_inputs.join(', ')} unavailable — held at its average`
          : risk.rain_source === 'radar'
          ? 'Rain from radar at home — airport gauge unreliable'
          : `From rain, river flow & season · ${risk.trained.samples} DEQ samples ${risk.trained.years[0]}–${risk.trained.years[1]}`
      }
      note={`Also Caution after ≥${risk.summer_floor_rain_in}" of rain in 72h, May–Sep`}
    >
      <Meter
        value={risk.probability}
        max={scaleMax}
        threshold={risk.caution_probability}
        thresholdLabel={`Caution ${(risk.caution_probability * 100).toFixed(1)}%`}
        fillClass={overLine ? 'bg-status-warning' : 'bg-accent'}
        label="Predicted bacteria risk against the Caution line"
      />
    </SignalCard>
  )
}

function IncidentsCard({ reports }: { reports: Conditions['reports'] }) {
  const incidents = reports.incidents
  const scope = `NC DEQ · within ${reports.radius_mi} mi · last ${reports.lookback_days} days`
  if (incidents == null) {
    return <SignalCard title="Fish kills & algal blooms" icon={Fish} status="unknown" value="Unavailable" caption="NC DEQ feed unreachable" />
  }
  const recentBloom = incidents.some((i) => i.algal_bloom && i.age_days <= INCIDENT_SCORE_DAYS)
  const latest = incidents[0]
  return (
    <SignalCard
      title="Fish kills & algal blooms"
      icon={Fish}
      status={recentBloom ? 'danger' : incidents.length > 0 ? 'warn' : 'ok'}
      statusLabel={recentBloom ? 'Bloom' : incidents.length > 0 ? 'Reported' : 'None'}
      value={incidents.length > 0 ? `${incidents.length} report${incidents.length === 1 ? '' : 's'}` : 'None'}
      caption={latest ? `Latest: ${latest.type.toLowerCase()} · ${shortDate(latest.date)}` : 'Nothing reported nearby'}
      detail={scope}
      note="Usually low-oxygen events; some blooms are toxic — avoid discolored water"
    />
  )
}

function SpillsCard({ reports }: { reports: Conditions['reports'] }) {
  const spills = reports.sewer_spills
  const scope = `NC DEQ · within ${reports.radius_mi} mi · last ${reports.lookback_days} days`
  if (spills == null) {
    return <SignalCard title="Sewage spills" icon={Biohazard} status="unknown" value="Unavailable" caption="NC DEQ feed unreachable" />
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
      title="Sewage spills"
      icon={Biohazard}
      status={scored ? 'danger' : reached.length > 0 ? 'warn' : 'ok'}
      statusLabel={scored ? 'In the water' : reached.length > 0 ? 'Recent' : 'None'}
      value={reached.length > 0 ? `${reached.length} reached water` : 'None'}
      caption={
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
  const [history, setHistory] = useState<HistorySnapshot[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const season = swimSeasonInfo(new Date())

  const loadHistory = useCallback(async () => {
    try {
      setHistory(await fetchHistory(HISTORY_DAYS))
    } catch {
      // Trends are a bonus; the dashboard works without them
    }
  }, [])

  const load = useCallback(async () => {
    try {
      setData(await fetchConditions())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load conditions')
    } finally {
      setLoading(false)
    }
    loadHistory()
  }, [loadHistory])

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      setData(await forceRefresh())
      setError(null)
      loadHistory()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Refresh failed')
    } finally {
      setRefreshing(false)
    }
  }

  useEffect(() => {
    load()
    const id = setInterval(load, REFRESH_INTERVAL_MS)
    return () => clearInterval(id)
  }, [load])

  const w = data?.weather
  const upstream = data?.gauges.upstream

  return (
    <div className="min-h-screen">
      <Hero data={data} refreshing={refreshing} onRefresh={handleRefresh} />

      <main className="relative mx-auto -mt-20 max-w-6xl space-y-12 px-4 pb-16 sm:px-6">
        {loading && !data && (
          <div className="card grid h-48 place-items-center text-sm text-ink-2 animate-pulse">Reading the river…</div>
        )}

        {error && !loading && (
          <div className="card border-l-4 border-l-status-critical p-4 text-sm text-ink">{error}</div>
        )}

        {data && w && upstream && (
          <div className={refreshing ? 'opacity-70 transition-opacity' : 'transition-opacity'}>
            <div className="space-y-12">
              {data.alerts && <AlertsBanner alerts={data.alerts} />}

              <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
                <FactorBreakdown score={data.score} factors={data.score_factors} />
                <Trends history={history} days={HISTORY_DAYS} />
              </div>

              <Section icon={Microscope} title="Water quality" subtitle="What's in the water off River Bend">
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  <BacteriaCard primary={data.bacteria.primary} />
                  <RiskCard risk={data.bacteria_risk} />
                  <SignalCard
                    title="Vibrio"
                    icon={ShieldAlert}
                    status={vibrioStatus(data.vibrio.level)}
                    statusLabel={data.vibrio.level.charAt(0).toUpperCase() + data.vibrio.level.slice(1)}
                    value={data.vibrio.level.charAt(0).toUpperCase() + data.vibrio.level.slice(1)}
                    caption={data.vibrio.reason}
                    detail={
                      data.water.salinity_site && data.water.salinity_date
                        ? `Salinity at ${data.water.salinity_site.split(',')[0]} · ${shortDate(data.water.salinity_date)}`
                        : undefined
                    }
                    note="A concern for open wounds, liver disease or weak immunity — not in the score"
                  />
                  <SignalCard
                    title="Water temperature"
                    icon={Thermometer}
                    status={data.water.temp_f == null ? 'unknown' : data.water.temp_f < 60 ? 'warn' : 'ok'}
                    statusLabel={
                      data.water.temp_f == null
                        ? undefined
                        : data.water.temp_f >= 75
                        ? 'Warm'
                        : data.water.temp_f >= 65
                        ? 'Mild'
                        : 'Cool'
                    }
                    value={data.water.temp_f != null ? `${Math.round(data.water.temp_f)}°F` : 'No data'}
                    caption={
                      data.water.temp_source
                        ? `${data.water.temp_source}${data.water.temp_date ? ` · ${shortDate(data.water.temp_date)}` : ''}`
                        : 'No sensor reachable'
                    }
                    note={
                      data.water.temp_date
                        ? 'Measured on site when DEQ sampled'
                        : 'Ocean-inlet proxy ~40 mi SE — the shallow Trent runs warmer in summer, cooler in winter'
                    }
                  />
                  <IncidentsCard reports={data.reports} />
                  <SpillsCard reports={data.reports} />
                </div>
              </Section>

              <Section icon={CloudRain} title="Weather" subtitle="Rain drives runoff; lightning drives you out of the water">
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  <SignalCard
                    title="Rain, last 24 hours"
                    icon={CloudDrizzle}
                    status={w.rain_gauge_issue ? 'unknown' : rainStatus(w.rain_24h_in)}
                    statusLabel={w.rain_gauge_issue ? 'Gauge issue' : undefined}
                    value={w.rain_24h_in != null ? `${w.rain_24h_in.toFixed(2)}"` : 'No data'}
                    caption={
                      w.rain_gauge_issue
                        ? 'Airport gauge unreliable — may be undercounted'
                        : w.rain_24h_in != null && w.rain_24h_in > 1.0
                        ? 'Heavy — runoff risk'
                        : w.rain_24h_in != null && w.rain_24h_in > 0.25
                        ? 'Moderate rain'
                        : 'Light or dry'
                    }
                    detail={
                      w.radar_rain_24h_in != null
                        ? `KEWN airport gauge · radar at home ${w.radar_rain_24h_in.toFixed(2)}"`
                        : 'KEWN airport gauge'
                    }
                    note={w.rain_gauge_issue ?? undefined}
                  />
                  <SignalCard
                    title="Rain, last 72 hours"
                    icon={CloudRain}
                    status={w.rain_gauge_issue ? 'unknown' : rain72Status(w.rain_72h_in)}
                    statusLabel={w.rain_gauge_issue ? 'Gauge issue' : undefined}
                    value={w.rain_72h_in != null ? `${w.rain_72h_in.toFixed(2)}"` : 'No data'}
                    caption={
                      w.rain_gauge_issue
                        ? 'Airport gauge unreliable — may be undercounted'
                        : w.rain_72h_in != null && w.rain_72h_in > 2.0
                        ? 'Peak contamination window'
                        : w.rain_72h_in != null && w.rain_72h_in > 1.0
                        ? 'Elevated 72-hour total'
                        : 'Dry spell — low runoff'
                    }
                    detail={[
                      w.rain_7d_in != null && `7 days ${w.rain_7d_in.toFixed(2)}"`,
                      w.radar_rain_72h_in != null &&
                        `radar at home ${w.radar_rain_72h_in.toFixed(2)}" (7 days ${w.radar_rain_7d_in?.toFixed(2) ?? '—'}")`,
                    ].filter(Boolean).join(' · ') || undefined}
                    note="Bacteria peak 48–72 hours after rain in eastern NC"
                  />
                  <SignalCard
                    title="Rain forecast, 72 hours"
                    icon={CalendarClock}
                    status={forecastStatus(w)}
                    statusLabel={
                      w.qpf_72h_in == null
                        ? undefined
                        : w.qpf_72h_in > 1.0
                        ? 'Heavy rain coming'
                        : w.qpf_72h_in > 0.25
                        ? 'Rain coming'
                        : 'Dry'
                    }
                    value={
                      w.qpf_72h_in != null
                        ? `${w.qpf_72h_in.toFixed(2)}"`
                        : w.rain_forecast_pct != null
                        ? `${w.rain_forecast_pct}% chance`
                        : 'No forecast'
                    }
                    caption={
                      w.qpf_72h_in != null && w.qpf_72h_in >= 0.25
                        ? 'Expected — bacteria risk rises 2–3 days after'
                        : w.rain_forecast_pct != null
                        ? `Peak chance ${w.rain_forecast_pct}% · ${w.rain_forecast_period}`
                        : 'No rain in the forecast'
                    }
                    detail="NWS forecast for River Bend's grid cell"
                    note="Plan swims before rain, or 3+ days after"
                  />
                  <SignalCard
                    title="Lightning"
                    icon={Zap}
                    status={thunderStatus(w.thunder_pct_6h)}
                    value={w.thunder_pct_6h != null ? `${w.thunder_pct_6h}%` : 'No data'}
                    caption="Chance of thunder in the next 6 hours"
                    detail={w.thunder_pct_24h != null ? `Next 24 hours: ${w.thunder_pct_24h}%` : undefined}
                    note="Hear thunder? Get out of the water"
                  />
                  <SignalCard
                    title="Wind"
                    icon={Wind}
                    status={windStatus(w.wind_speed_mph)}
                    value={w.wind_speed_mph != null ? `${w.wind_speed_mph.toFixed(0)} mph` : 'No data'}
                    caption={w.wind_direction ? `From the ${w.wind_direction}` : undefined}
                    detail="NOAA surface observation, KEWN"
                    note="Wind mixes the estuary near the Neuse confluence"
                  />
                </div>
              </Section>

              <Section icon={Activity} title="The river" subtitle="Upstream flow carries runoff down to River Bend">
                <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
                  <SignalCard
                    title="Upstream flow"
                    icon={Activity}
                    status={
                      upstream.discharge_cfs == null
                        ? 'unknown'
                        : upstream.discharge_p80 != null && upstream.discharge_cfs > upstream.discharge_p80
                        ? 'warn'
                        : 'ok'
                    }
                    statusLabel={
                      upstream.discharge_cfs != null && upstream.discharge_p80 != null
                        ? upstream.discharge_cfs > upstream.discharge_p80
                          ? 'High'
                          : 'Normal'
                        : undefined
                    }
                    value={upstream.discharge_cfs != null ? `${upstream.discharge_cfs.toFixed(0)} ft³/s` : 'No data'}
                    caption="Trent River near Trenton, ~17 mi upstream"
                  >
                    {upstream.discharge_cfs != null && upstream.discharge_p80 != null && (
                      <Meter
                        value={upstream.discharge_cfs}
                        max={upstream.discharge_p80 * 2}
                        threshold={upstream.discharge_p80}
                        thresholdLabel={`High: ${upstream.discharge_p80.toFixed(0)} ft³/s`}
                        fillClass={upstream.discharge_cfs > upstream.discharge_p80 ? 'bg-status-warning' : 'bg-accent'}
                        label="Upstream flow against the high-flow line for today's date"
                      />
                    )}
                  </SignalCard>
                  <GaugeSection upstream={upstream} local={data.gauges.local} />
                </div>
              </Section>

              <div className="grid items-start gap-4 lg:grid-cols-2">
                <BacteriaSites readings={data.bacteria.readings} primary={data.bacteria.primary} seasonLabel={season.label} />
                <ReportsSection reports={data.reports} />
              </div>
            </div>
          </div>
        )}
      </main>

      <footer className="border-t border-line/10">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-8 text-xs text-ink-2 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p>
            Data from{' '}
            {[
              ['USGS', 'https://waterdata.usgs.gov/'],
              ['Sound Rivers', 'https://soundrivers.org/swim-guide/'],
              ['NC DEQ', 'https://ncdenr.maps.arcgis.com/apps/dashboards/99430d6fd1824b78ae328c6a5538852f'],
              ['NOAA', 'https://api.weather.gov/'],
              ['Iowa Environmental Mesonet', 'https://mesonet.agron.iastate.edu/iemre/'],
            ].map(([name, href], i, all) => (
              <span key={name}>
                <a href={href} target="_blank" rel="noreferrer" className="font-medium text-accent hover:underline">
                  {name}
                </a>
                {i < all.length - 1 ? ' · ' : ''}
              </span>
            ))}
          </p>
          <p className="text-muted">Refreshes every 10 minutes · not a substitute for posted advisories</p>
        </div>
      </footer>
    </div>
  )
}
