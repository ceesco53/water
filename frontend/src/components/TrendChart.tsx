import { useEffect, useMemo, useRef, useState } from 'react'
import { format } from 'date-fns'
import { Table2 } from 'lucide-react'

export interface TrendPoint {
  t: Date
  v: number
}

interface Props {
  title: string
  subtitle: string
  points: TrendPoint[]
  yMax: number
  formatValue: (v: number) => string
  reference?: { value: number; label: string }
}

const PLOT_H = 150
const AXIS_H = 24
const PAD = { left: 40, right: 52, top: 12 }

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(0)
  useEffect(() => {
    if (!ref.current) return
    const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [])
  return [ref, width] as const
}

/** Ticks at clean steps from 0 to max, about three intervals. */
function yTicks(max: number): number[] {
  const raw = max / 3
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw
  const ticks = []
  for (let v = 0; v <= max + 1e-9; v += step) ticks.push(v)
  return ticks
}

function xTicks(start: Date, end: Date): Date[] {
  const spanH = (end.getTime() - start.getTime()) / 3_600_000
  const stepH = spanH > 72 ? 24 : spanH > 24 ? 12 : 6
  const first = new Date(start)
  first.setMinutes(0, 0, 0)
  first.setHours(Math.ceil(first.getHours() / stepH) * stepH)
  const ticks = []
  for (let t = first.getTime(); t <= end.getTime(); t += stepH * 3_600_000) ticks.push(new Date(t))
  return ticks
}

/**
 * One series over time: 2px line, 10% area wash, end dot with a direct label,
 * hairline grid, and a crosshair readout on hover or keyboard focus (arrow
 * keys step through points). A table view carries every value without hover.
 */
export function TrendChart({ title, subtitle, points, yMax, formatValue, reference }: Props) {
  const [wrapRef, width] = useWidth<HTMLDivElement>()
  const [active, setActive] = useState<number | null>(null)

  const geom = useMemo(() => {
    if (points.length < 2 || width === 0) return null
    const t0 = points[0].t.getTime()
    const t1 = points[points.length - 1].t.getTime()
    const plotW = Math.max(1, width - PAD.left - PAD.right)
    const x = (t: Date) => PAD.left + ((t.getTime() - t0) / Math.max(1, t1 - t0)) * plotW
    const y = (v: number) => PAD.top + PLOT_H - (Math.min(v, yMax) / yMax) * PLOT_H
    const line = points.map((p, i) => `${i ? 'L' : 'M'}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join(' ')
    const area = `${line} L${x(points[points.length - 1].t).toFixed(1)},${y(0)} L${x(points[0].t).toFixed(1)},${y(0)} Z`
    return { x, y, line, area, plotW }
  }, [points, width, yMax])

  const nearest = (clientX: number, rect: DOMRect) => {
    if (!geom) return null
    const px = clientX - rect.left
    let best = 0
    for (let i = 1; i < points.length; i++) {
      if (Math.abs(geom.x(points[i].t) - px) < Math.abs(geom.x(points[best].t) - px)) best = i
    }
    return best
  }

  const last = points[points.length - 1]
  const shown = active != null ? points[active] : null

  return (
    <section className="card p-5 sm:p-6">
      <h3 className="text-base font-semibold text-ink">{title}</h3>
      <p className="mt-0.5 text-xs text-ink-2">{subtitle}</p>

      <div ref={wrapRef} className="relative mt-4" style={{ height: PAD.top + PLOT_H + AXIS_H }}>
        {points.length < 2 ? (
          <div className="grid h-full place-items-center rounded-xl bg-surface-2/50 px-6 text-center text-sm text-ink-2">
            Building history — the trend fills in as readings are logged every 30 minutes.
          </div>
        ) : (
          geom && (
            <>
              <svg
                width={width}
                height={PAD.top + PLOT_H + AXIS_H}
                className="block touch-none select-none outline-none focus-visible:ring-2 focus-visible:ring-accent rounded-md"
                tabIndex={0}
                role="img"
                aria-label={`${title}: latest ${formatValue(last.v)} at ${format(last.t, 'EEE h:mm a')}`}
                onPointerMove={(e) => setActive(nearest(e.clientX, e.currentTarget.getBoundingClientRect()))}
                onPointerLeave={() => setActive(null)}
                onFocus={() => setActive(points.length - 1)}
                onBlur={() => setActive(null)}
                onKeyDown={(e) => {
                  if (e.key === 'ArrowLeft') setActive((i) => Math.max(0, (i ?? points.length - 1) - 1))
                  if (e.key === 'ArrowRight') setActive((i) => Math.min(points.length - 1, (i ?? points.length - 1) + 1))
                }}
              >
                {yTicks(yMax).map((v) => (
                  <g key={v}>
                    <line x1={PAD.left} x2={PAD.left + geom.plotW} y1={geom.y(v)} y2={geom.y(v)} className="stroke-grid" strokeWidth={1} />
                    <text x={PAD.left - 8} y={geom.y(v) + 4} textAnchor="end" className="fill-muted text-[11px] tabular-nums">
                      {formatValue(v)}
                    </text>
                  </g>
                ))}
                <line x1={PAD.left} x2={PAD.left + geom.plotW} y1={geom.y(0)} y2={geom.y(0)} className="stroke-axis" strokeWidth={1} />

                {xTicks(points[0].t, last.t).map((t) => (
                  <text key={t.getTime()} x={geom.x(t)} y={PAD.top + PLOT_H + 17} textAnchor="middle" className="fill-muted text-[11px]">
                    {format(t, t.getHours() === 0 ? 'EEE' : 'ha')}
                  </text>
                ))}

                {reference && (
                  <g>
                    <line
                      x1={PAD.left}
                      x2={PAD.left + geom.plotW}
                      y1={geom.y(reference.value)}
                      y2={geom.y(reference.value)}
                      className="stroke-status-warning"
                      strokeWidth={1}
                    />
                    <text x={PAD.left + 4} y={geom.y(reference.value) - 5} className="fill-ink-2 text-[11px]">
                      {reference.label}
                    </text>
                  </g>
                )}

                <path d={geom.area} className="fill-accent/10" />
                <path d={geom.line} fill="none" className="stroke-accent" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />

                {/* Latest value: end dot with a surface ring and a direct label */}
                <circle cx={geom.x(last.t)} cy={geom.y(last.v)} r={4} className="fill-accent stroke-surface" strokeWidth={2} />
                <text x={geom.x(last.t) + 8} y={geom.y(last.v) + 4} className="fill-ink text-xs font-semibold">
                  {formatValue(last.v)}
                </text>

                {shown && (
                  <g pointerEvents="none">
                    <line
                      x1={geom.x(shown.t)}
                      x2={geom.x(shown.t)}
                      y1={PAD.top}
                      y2={PAD.top + PLOT_H}
                      className="stroke-axis"
                      strokeWidth={1}
                    />
                    <circle cx={geom.x(shown.t)} cy={geom.y(shown.v)} r={4} className="fill-accent stroke-surface" strokeWidth={2} />
                  </g>
                )}
              </svg>

              {shown && (
                <div
                  className="pointer-events-none absolute top-0 rounded-lg border border-line/10 bg-surface px-2.5 py-1.5 shadow-md"
                  style={{
                    left: Math.min(Math.max(geom.x(shown.t) - 60, 0), width - 120),
                    width: 120,
                  }}
                >
                  <div className="text-sm font-semibold text-ink">{formatValue(shown.v)}</div>
                  <div className="text-[11px] text-ink-2">{format(shown.t, 'EEE MMM d, h:mm a')}</div>
                </div>
              )}
            </>
          )
        )}
      </div>

      {points.length >= 2 && (
        <details className="group mt-3">
          <summary className="inline-flex cursor-pointer items-center gap-1.5 text-xs text-ink-2 hover:text-ink">
            <Table2 className="h-3.5 w-3.5" aria-hidden />
            View as table
          </summary>
          <div className="mt-2 max-h-56 overflow-y-auto rounded-lg border border-line/10">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-surface-2 text-left text-ink-2">
                <tr>
                  <th className="px-3 py-1.5 font-medium">Time</th>
                  <th className="px-3 py-1.5 text-right font-medium">{title}</th>
                </tr>
              </thead>
              <tbody className="tabular-nums text-ink">
                {[...points].reverse().map((p) => (
                  <tr key={p.t.getTime()} className="border-t border-line/5">
                    <td className="px-3 py-1">{format(p.t, 'EEE MMM d, h:mm a')}</td>
                    <td className="px-3 py-1 text-right">{formatValue(p.v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </section>
  )
}
