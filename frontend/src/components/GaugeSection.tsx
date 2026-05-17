import type { Gauge } from '../types'

interface Props {
  upstream: Gauge
  local: Gauge
}

function GaugeRow({ gauge }: { gauge: Gauge }) {
  const elevated =
    gauge.discharge_cfs != null &&
    gauge.discharge_p80 != null &&
    gauge.discharge_cfs > gauge.discharge_p80

  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4 py-3 border-b border-surface-border last:border-0">
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-slate-200 truncate">{gauge.site_name}</div>
        <div className="text-xs text-slate-500">{gauge.description} · {gauge.site_code}</div>
      </div>
      <div className="flex gap-4 text-right flex-shrink-0">
        {gauge.discharge_cfs != null && (
          <div>
            <div className={`text-sm font-bold tabular-nums ${elevated ? 'text-yellow-400' : 'text-slate-200'}`}>
              {gauge.discharge_cfs.toFixed(0)}
            </div>
            <div className="text-xs text-slate-500">ft³/s</div>
          </div>
        )}
        {gauge.gage_height_ft != null && (
          <div>
            <div className="text-sm font-bold text-slate-200 tabular-nums">
              {gauge.gage_height_ft.toFixed(2)}
            </div>
            <div className="text-xs text-slate-500">ft stage</div>
          </div>
        )}
        {gauge.discharge_cfs == null && gauge.gage_height_ft == null && (
          <div className="text-xs text-slate-600">No data</div>
        )}
      </div>
    </div>
  )
}

export function GaugeSection({ upstream, local }: Props) {
  return (
    <div className="rounded-xl border border-surface-border bg-surface-card p-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-lg">📊</span>
        <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
          USGS River Gauges
        </span>
      </div>
      <div>
        <GaugeRow gauge={upstream} />
        <GaugeRow gauge={local} />
      </div>
      <div className="mt-3 text-xs text-slate-600">
        Yellow discharge = above 7-day 80th percentile (elevated runoff)
      </div>
    </div>
  )
}
