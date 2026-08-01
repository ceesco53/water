import { useCallback, useEffect, useRef, useState } from 'react'
import clsx from 'clsx'
import { formatDistanceToNow } from 'date-fns'
import { fetchConditions, forceRefresh } from './api'
import type { Conditions } from './types'
import { ScoreCard } from './components/ScoreCard'
import { SignalCard } from './components/SignalCard'
import { GaugeSection } from './components/GaugeSection'

const REFRESH_INTERVAL_MS = 10 * 60 * 1000 // 10 minutes

function swimguideStatus(status: string): 'ok' | 'warn' | 'danger' | 'unknown' {
  if (status === 'safe') return 'ok'
  if (status === 'caution') return 'warn'
  if (status === 'unsafe') return 'danger'
  return 'unknown'
}

function swimguideLabel(status: string) {
  return {
    safe: 'Safe',
    caution: 'Caution',
    unsafe: 'Unsafe',
    unknown: 'Unknown',
    api_unavailable: 'Check Directly',
  }[status] ?? status
}

function rainStatus(inches: number | null): 'ok' | 'warn' | 'danger' | 'unknown' {
  if (inches == null) return 'unknown'
  if (inches > 1.0) return 'danger'
  if (inches > 0.25) return 'warn'
  return 'ok'
}

function windStatus(mph: number | null): 'ok' | 'warn' | 'danger' | 'unknown' {
  if (mph == null) return 'unknown'
  if (mph > 20) return 'warn'
  return 'ok'
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
            {/* Score card */}
            <ScoreCard
              score={data.score}
              rating={data.rating}
              color={data.rating_color}
              factors={data.score_factors}
            />

            {/* Signal grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {/* Swim Guide / Bacteria */}
              {data.swimguide.status === 'api_unavailable' ? (
                <div className="rounded-xl border border-blue-900/50 bg-blue-950/20 p-4 flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-lg">🦠</span>
                      <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                        Swim Guide (Bacteria)
                      </span>
                    </div>
                    <span className="w-2 h-2 rounded-full bg-blue-400 flex-shrink-0" />
                  </div>
                  <div className="flex items-start gap-2 bg-blue-900/30 rounded-lg px-3 py-2">
                    <span className="text-blue-300 mt-0.5">📅</span>
                    <div>
                      <div className="text-sm font-semibold text-blue-200">
                        {season.inSeason ? 'In season now' : season.label}
                      </div>
                      <div className="text-xs text-blue-400">
                        50+ sites sampled weekly Thu–Fri, Memorial Day through Labor Day
                      </div>
                    </div>
                  </div>
                  <div className="text-sm text-slate-300 leading-relaxed">
                    <a
                      href={data.swimguide.source_url ?? 'https://soundrivers.org/swim-guide/'}
                      target="_blank"
                      rel="noreferrer"
                      className="text-blue-400 underline hover:text-blue-300"
                    >
                      Check Sound Rivers directly →
                    </a>
                  </div>
                  <div className="text-xs text-slate-600 border-t border-surface-border pt-2 italic">
                    {season.inSeason
                      ? 'No sample on file right now — rainfall signals below serve as the bacteria proxy'
                      : 'Until then, rainfall signals below serve as the bacteria proxy'}
                  </div>
                </div>
              ) : (
                <SignalCard
                  title={data.swimguide.source ? 'Bacteria (NC BEACH)' : 'Swim Guide (Bacteria)'}
                  icon="🦠"
                  status={swimguideStatus(data.swimguide.status)}
                  primary={
                    data.swimguide.latest_mpn != null
                      ? `${data.swimguide.latest_mpn} MPN/100mL`
                      : swimguideLabel(data.swimguide.status)
                  }
                  secondary={
                    data.swimguide.latest_date != null
                      ? `Sampled ${data.swimguide.latest_date}${data.swimguide.age_days != null ? ` · ${data.swimguide.age_days}d ago` : ''}`
                      : data.swimguide.beaches.length > 1
                      ? `${data.swimguide.beaches.length} sites — worst shown`
                      : undefined
                  }
                  detail={
                    data.swimguide.source
                      ? 'EPA WQP · NC BEACH Program (C99 + C100A)'
                      : `${data.swimguide.beaches.length} station(s) checked`
                  }
                  note={
                    data.swimguide.age_days != null && data.swimguide.age_days > 14
                      ? season.inSeason
                        ? `Data ${data.swimguide.age_days}d old — EPA's feed lags; check soundrivers.org for this week's sample`
                        : `Data ${data.swimguide.age_days}d old — Sound Rivers is off-season`
                      : '≤35 safe · 35–130 caution · >130 unsafe (MPN/100mL)'
                  }
                />
              )}

              {/* Rainfall 24h */}
              <SignalCard
                title="Rainfall — Last 24h"
                icon="🌧️"
                status={rainStatus(data.weather.rain_24h_in)}
                primary={
                  data.weather.rain_24h_in != null
                    ? `${data.weather.rain_24h_in.toFixed(2)}"`
                    : 'No data'
                }
                secondary={
                  data.weather.rain_24h_in != null && data.weather.rain_24h_in > 1.0
                    ? 'Heavy — runoff risk'
                    : data.weather.rain_24h_in != null && data.weather.rain_24h_in > 0.25
                    ? 'Moderate rain'
                    : 'Light / dry'
                }
                detail="KEWN (Craven County Airport)"
              />

              {/* Rainfall 72h */}
              <SignalCard
                title="Rainfall — Last 72h"
                icon="⛈️"
                status={rainStatus(data.weather.rain_72h_in)}
                primary={
                  data.weather.rain_72h_in != null
                    ? `${data.weather.rain_72h_in.toFixed(2)}"`
                    : 'No data'
                }
                secondary={
                  data.weather.rain_72h_in != null && data.weather.rain_72h_in > 2.0
                    ? 'Peak contamination window'
                    : data.weather.rain_72h_in != null && data.weather.rain_72h_in > 1.0
                    ? 'Elevated 72h accumulation'
                    : 'Dry period — low risk'
                }
                note="48–72h post-rain = peak risk in eastern NC"
              />

              {/* Rain forecast */}
              <SignalCard
                title="Rain Forecast (72h)"
                icon="📅"
                status={
                  data.weather.rain_forecast_pct == null
                    ? 'unknown'
                    : data.weather.rain_forecast_pct >= 60
                    ? 'warn'
                    : data.weather.rain_forecast_pct >= 30
                    ? 'warn'
                    : 'ok'
                }
                primary={
                  data.weather.rain_forecast_pct != null
                    ? `${data.weather.rain_forecast_pct}% chance`
                    : 'No forecast'
                }
                secondary={
                  data.weather.rain_forecast_pct != null && data.weather.rain_forecast_pct >= 30
                    ? `${data.weather.rain_forecast_period} — bacteria risk elevated 48–72h after`
                    : data.weather.rain_forecast_pct != null
                    ? data.weather.rain_forecast_period ?? 'Low rain risk ahead'
                    : undefined
                }
                detail="NWS MHX · next 72h"
                note="Plan swims before rain or 3+ days after"
              />

              {/* Water temp */}
              <SignalCard
                title="Water Temperature"
                icon="🌡️"
                status={
                  data.water_temp_f == null
                    ? 'unknown'
                    : data.water_temp_f < 60
                    ? 'warn'
                    : 'ok'
                }
                primary={
                  data.water_temp_f != null ? `${data.water_temp_f}°F` : 'No data'
                }
                secondary={
                  data.water_temp_f != null
                    ? data.water_temp_f >= 75
                      ? 'Warm — comfortable'
                      : data.water_temp_f >= 65
                      ? 'Moderate'
                      : 'Cool'
                    : 'No USGS sensor on Trent River'
                }
                detail={data.water_temp_source ?? 'NOAA CO-OPS coastal proxy'}
                note="No water temp sensor on any Trent River USGS gauge"
              />

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
                    ? `80th pct: ${data.gauges.upstream.discharge_p80.toFixed(0)} ft³/s`
                    : undefined
                }
                detail="Trent near Trenton — runoff indicator"
              />
            </div>

            {/* USGS Gauge Detail Table */}
            <GaugeSection
              upstream={data.gauges.upstream}
              local={data.gauges.local}
            />

            {/* Swim Guide beaches */}
            {data.swimguide.beaches.length > 0 && (
              <div className="rounded-xl border border-surface-border bg-surface-card p-4">
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-lg">📍</span>
                  <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                    Monitored Swim Sites
                  </span>
                </div>
                <div className="space-y-2">
                  {data.swimguide.beaches.map((beach) => (
                    <div
                      key={beach.id}
                      className="flex items-center justify-between py-2 border-b border-surface-border last:border-0"
                    >
                      <span className="text-sm text-slate-300">{beach.name}</span>
                      <span
                        className={clsx(
                          'text-xs px-2 py-0.5 rounded-full font-medium border',
                          beach.status === 'safe'
                            ? 'bg-green-500/20 text-green-300 border-green-500/30'
                            : beach.status === 'unsafe'
                            ? 'bg-red-500/20 text-red-300 border-red-500/30'
                            : beach.status === 'caution'
                            ? 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30'
                            : 'bg-slate-700 text-slate-400 border-slate-600'
                        )}
                      >
                        {beach.status.charAt(0).toUpperCase() + beach.status.slice(1)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </main>

      {/* Footer */}
      <footer className="max-w-5xl mx-auto px-4 py-6 mt-4 border-t border-surface-border">
        <p className="text-xs text-slate-600 text-center">
          Data from{' '}
          <a
            href="https://waterservices.usgs.gov/"
            className="text-slate-500 hover:text-slate-300 underline"
            target="_blank"
            rel="noreferrer"
          >
            USGS NWIS
          </a>
          {' · '}
          <a
            href="https://www.theswimguide.org/"
            className="text-slate-500 hover:text-slate-300 underline"
            target="_blank"
            rel="noreferrer"
          >
            Swim Guide / Sound Rivers
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
