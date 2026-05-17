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

export default function App() {
  const [data, setData] = useState<Conditions | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

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
              {/* Swim Guide */}
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
                      <div className="text-sm font-semibold text-blue-200">2026 season starts May 22</div>
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
                    Until then, rainfall signals below serve as the bacteria proxy
                  </div>
                </div>
              ) : (
                <SignalCard
                  title="Swim Guide (Bacteria)"
                  icon="🦠"
                  status={swimguideStatus(data.swimguide.status)}
                  primary={swimguideLabel(data.swimguide.status)}
                  secondary={
                    data.swimguide.beaches.length > 0
                      ? data.swimguide.beaches.map((b) => b.name).join(', ')
                      : undefined
                  }
                  detail={`${data.swimguide.beaches.length} station(s) checked`}
                  note="Highest-weight safety signal"
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
