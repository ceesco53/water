import { Gauge as GaugeIcon } from 'lucide-react'
import type { Gauge } from '../types'

function GaugeRow({ gauge }: { gauge: Gauge }) {
  const readings = [
    gauge.discharge_cfs != null && { value: gauge.discharge_cfs.toFixed(0), unit: 'ft³/s flow' },
    gauge.gage_height_ft != null && { value: gauge.gage_height_ft.toFixed(2), unit: 'ft stage' },
  ].filter(Boolean) as { value: string; unit: string }[]

  return (
    <li className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="text-sm font-medium text-ink">{gauge.site_name}</div>
        <div className="text-xs text-ink-2">
          {gauge.description} · USGS {gauge.site_code}
        </div>
      </div>
      <div className="flex gap-6">
        {readings.length === 0 && <span className="text-xs text-muted">No data</span>}
        {readings.map((r) => (
          <div key={r.unit} className="text-right">
            <div className="text-base font-semibold tabular-nums text-ink">{r.value}</div>
            <div className="text-[11px] text-muted">{r.unit}</div>
          </div>
        ))}
      </div>
    </li>
  )
}

export function GaugeSection({ upstream, local }: { upstream: Gauge; local: Gauge }) {
  return (
    <section className="card p-5 sm:p-6" aria-labelledby="gauges-title">
      <div className="flex items-center gap-2">
        <GaugeIcon className="h-4 w-4 text-accent" aria-hidden />
        <h2 id="gauges-title" className="text-base font-semibold text-ink">
          USGS river gauges
        </h2>
      </div>
      <ul className="mt-2 divide-y divide-line/[0.06]">
        <GaugeRow gauge={upstream} />
        <GaugeRow gauge={local} />
      </ul>
    </section>
  )
}
