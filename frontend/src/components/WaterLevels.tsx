import { Activity, ArrowDownRight, ArrowRight, ArrowUpRight, ExternalLink, Waves } from 'lucide-react'
import type { FloodCategory, Gauge, WaterLevelGauge } from '../types'
import type { StatusLevel } from '../status'
import { LineChart, type Reference } from './LineChart'
import { Meter } from './Meter'
import { StatusPill } from './StatusPill'

const CATEGORY: Record<FloodCategory, { level: StatusLevel; label: string }> = {
  normal: { level: 'ok', label: 'Normal' },
  action: { level: 'warn', label: 'Action stage' },
  minor: { level: 'danger', label: 'Minor flooding' },
  moderate: { level: 'danger', label: 'Moderate flooding' },
  major: { level: 'danger', label: 'Major flooding' },
}

const ft = (v: number) => `${v.toFixed(1)} ft`

function Change({ feet }: { feet: number | null }) {
  if (feet == null) return null
  const Icon = Math.abs(feet) < 0.05 ? ArrowRight : feet > 0 ? ArrowUpRight : ArrowDownRight
  const text = Math.abs(feet) < 0.05 ? 'Steady over 24 h' : `${feet > 0 ? 'Up' : 'Down'} ${Math.abs(feet).toFixed(2)} ft in 24 h`
  return (
    <span className="inline-flex items-center gap-1 text-xs text-ink-2">
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {text}
    </span>
  )
}

function GaugePanel({ gauge }: { gauge: WaterLevelGauge }) {
  const points = gauge.series.map(([t, v]) => ({ t: new Date(t), v }))
  const { action, minor } = gauge.flood_stages
  const values = points.map((p) => p.v)
  // Frame the data and the flood line it's measured against, on half-foot steps
  const lo = Math.min(...values)
  const hi = Math.max(...values, minor ?? action ?? -Infinity)
  const pad = Math.max(0.25, (hi - lo) * 0.1)
  const yMin = Math.floor((lo - pad) * 2) / 2
  const yMax = Math.ceil((hi + pad) * 2) / 2
  const references: Reference[] = [
    action != null && { value: action, label: `Action ${action}`, tone: 'warning' as const },
    minor != null && { value: minor, label: `Flood ${minor}`, tone: 'critical' as const },
  ].filter(Boolean) as Reference[]
  const status = CATEGORY[gauge.category]

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-medium text-ink">{gauge.short}</div>
          <div className="text-xs text-muted">
            {gauge.distance_mi} mi · {gauge.position}
          </div>
        </div>
        <StatusPill status={status.level} label={status.label} />
      </div>

      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-[26px] font-semibold leading-none tracking-tight text-ink">{gauge.latest_ft.toFixed(2)} ft</span>
        <Change feet={gauge.change_24h_ft} />
      </div>

      <LineChart
        points={points}
        yMin={yMin}
        yMax={yMax}
        formatValue={ft}
        label={`${gauge.name} water level`}
        references={references}
        plotHeight={112}
        endLabel={false}
      />

      <a
        href={gauge.url}
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-1 text-[11px] text-muted hover:text-accent"
      >
        {gauge.datum === 'MLLW' ? 'ft above mean lower low water' : 'ft gage height'}
        {gauge.operator && ` · ${gauge.operator}`}
        <ExternalLink className="h-3 w-3" aria-hidden />
      </a>
    </div>
  )
}

/** The three nearest Trent River gauges as small multiples, plus upstream flow. */
export function WaterLevels({ gauges, upstream }: { gauges: WaterLevelGauge[]; upstream: Gauge }) {
  const flowHigh = upstream.discharge_cfs != null && upstream.discharge_p80 != null && upstream.discharge_cfs > upstream.discharge_p80

  return (
    <section className="card p-5 sm:p-6" aria-labelledby="levels-title">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <div className="flex items-center gap-2">
            <Waves className="h-4 w-4 text-accent" aria-hidden />
            <h3 id="levels-title" className="text-base font-semibold text-ink">
              Water levels, last 7 days
            </h3>
          </div>
          <p className="mt-0.5 text-xs text-ink-2">
            The three Trent River gauges nearest you, with the National Weather Service's action and flood lines
          </p>
        </div>
      </div>

      {gauges.length === 0 ? (
        <p className="mt-5 rounded-xl bg-surface-2/50 px-4 py-8 text-center text-sm text-ink-2">
          River gauges are unreachable right now.
        </p>
      ) : (
        <div className="mt-5 grid gap-x-8 gap-y-8 md:grid-cols-3">
          {gauges.map((g) => (
            <GaugePanel key={g.id} gauge={g} />
          ))}
        </div>
      )}

      <div className="mt-6 grid gap-4 border-t border-line/10 pt-5 md:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] md:items-center">
        <div className="flex items-center gap-3">
          <span className="grid h-8 w-8 flex-shrink-0 place-items-center rounded-lg bg-accent/10">
            <Activity className="h-4 w-4 text-accent" aria-hidden />
          </span>
          <div className="min-w-0">
            <div className="text-sm font-medium text-ink">
              Upstream flow{' '}
              <span className="font-semibold">
                {upstream.discharge_cfs != null ? `${upstream.discharge_cfs.toFixed(0)} ft³/s` : '—'}
              </span>
            </div>
            <div className="text-xs text-ink-2">Trent River near Trenton, ~17 mi upstream</div>
          </div>
        </div>
        {upstream.discharge_cfs != null && upstream.discharge_p80 != null && (
          <div className="flex items-center gap-4">
            <div className="flex-1">
              <Meter
                value={upstream.discharge_cfs}
                max={upstream.discharge_p80 * 2}
                threshold={upstream.discharge_p80}
                thresholdLabel={`High for today: ${upstream.discharge_p80.toFixed(0)} ft³/s`}
                fillClass={flowHigh ? 'bg-status-warning' : 'bg-accent'}
                label="Upstream flow against the high-flow line for today's date"
              />
            </div>
            <StatusPill status={flowHigh ? 'warn' : 'ok'} label={flowHigh ? 'High' : 'Normal'} />
          </div>
        )}
      </div>

      <p className="mt-4 text-[11px] text-muted">
        Action stage means the river is high enough that the National Weather Service starts watching for flooding. Each
        gauge measures from its own reference point, so compare a gauge with its own lines, not with the others.
      </p>
    </section>
  )
}
