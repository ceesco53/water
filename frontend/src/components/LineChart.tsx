import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { format } from 'date-fns'

export interface TrendPoint {
  t: Date
  v: number
}

export interface Reference {
  value: number
  label: string
  tone: 'warning' | 'critical'
}

interface Props {
  points: TrendPoint[]
  yMin: number
  yMax: number
  formatValue: (v: number) => string
  // Accessible name, e.g. "Swim score"
  label: string
  references?: Reference[]
  plotHeight?: number
  // Direct label beside the latest point (skip when a header already shows it)
  endLabel?: boolean
  emptyMessage?: string
}

const AXIS_H = 22
const TOP = 10
const LEFT = 40

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(0)
  // Measure before first paint, so the chart never flashes empty while
  // waiting for the observer's first (next-frame) callback; then track resizes.
  useLayoutEffect(() => {
    if (!ref.current) return
    setWidth(ref.current.getBoundingClientRect().width)
    const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [])
  return [ref, width] as const
}

/** Ticks at clean steps across [min, max], about three intervals. */
function yTicks(min: number, max: number): number[] {
  const raw = (max - min) / 3
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw
  const ticks = []
  for (let v = Math.ceil(min / step - 1e-9) * step; v <= max + 1e-9; v += step) ticks.push(Math.round(v * 1e6) / 1e6)
  return ticks
}

function xTicks(start: Date, end: Date, plotW: number): Date[] {
  const spanH = (end.getTime() - start.getTime()) / 3_600_000
  let stepH = spanH > 72 ? 24 : spanH > 24 ? 12 : 6
  // Thin the labels when the plot is narrow, so they never collide
  while ((plotW / (spanH / stepH)) < 44 && stepH < 96) stepH *= 2
  const first = new Date(start)
  first.setMinutes(0, 0, 0)
  first.setHours(Math.ceil(first.getHours() / Math.min(stepH, 24)) * Math.min(stepH, 24))
  const ticks = []
  for (let t = first.getTime(); t <= end.getTime(); t += stepH * 3_600_000) ticks.push(new Date(t))
  return ticks
}

/**
 * One series over time: 2px line, 10% area wash, hairline grid, optional
 * threshold lines, an end dot (optionally labeled), and a crosshair readout
 * on hover or keyboard focus -- arrow keys step through the points.
 */
export function LineChart({
  points,
  yMin,
  yMax,
  formatValue,
  label,
  references = [],
  plotHeight = 150,
  endLabel = true,
  emptyMessage = 'Not enough readings yet.',
}: Props) {
  const [wrapRef, width] = useWidth<HTMLDivElement>()
  const [active, setActive] = useState<number | null>(null)
  const right = endLabel ? 52 : 14
  const height = TOP + plotHeight + AXIS_H

  const geom = useMemo(() => {
    if (points.length < 2 || width === 0) return null
    const t0 = points[0].t.getTime()
    const t1 = points[points.length - 1].t.getTime()
    const plotW = Math.max(1, width - LEFT - right)
    const x = (t: Date) => LEFT + ((t.getTime() - t0) / Math.max(1, t1 - t0)) * plotW
    const y = (v: number) => TOP + plotHeight - ((Math.min(Math.max(v, yMin), yMax) - yMin) / (yMax - yMin)) * plotHeight
    const line = points.map((p, i) => `${i ? 'L' : 'M'}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join(' ')
    const base = y(yMin)
    const area = `${line} L${x(points[points.length - 1].t).toFixed(1)},${base} L${x(points[0].t).toFixed(1)},${base} Z`
    return { x, y, line, area, plotW }
  }, [points, width, yMin, yMax, plotHeight, right])

  // Threshold labels sit above their line, unless the line just above is too
  // close -- then below, so neighbors never overlap.
  const placedRefs = useMemo(() => {
    if (!geom) return []
    const sorted = [...references].filter((r) => r.value >= yMin && r.value <= yMax).sort((a, b) => b.value - a.value)
    return sorted.map((r, i) => ({
      ...r,
      below: i > 0 && geom.y(r.value) - geom.y(sorted[i - 1].value) < 16,
    }))
  }, [references, geom, yMin, yMax])

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
    <div ref={wrapRef} className="relative" style={{ height }}>
      {points.length < 2 ? (
        <div className="grid h-full place-items-center rounded-xl bg-surface-2/50 px-6 text-center text-sm text-ink-2">
          {emptyMessage}
        </div>
      ) : (
        geom && (
          <>
            <svg
              width={width}
              height={height}
              className="block touch-none select-none rounded-md outline-none focus-visible:ring-2 focus-visible:ring-accent"
              tabIndex={0}
              role="img"
              aria-label={`${label}: latest ${formatValue(last.v)} at ${format(last.t, 'EEE h:mm a')}`}
              onPointerMove={(e) => setActive(nearest(e.clientX, e.currentTarget.getBoundingClientRect()))}
              onPointerLeave={() => setActive(null)}
              onFocus={() => setActive(points.length - 1)}
              onBlur={() => setActive(null)}
              onKeyDown={(e) => {
                if (e.key === 'ArrowLeft') setActive((i) => Math.max(0, (i ?? points.length - 1) - 1))
                if (e.key === 'ArrowRight') setActive((i) => Math.min(points.length - 1, (i ?? points.length - 1) + 1))
              }}
            >
              {yTicks(yMin, yMax).map((v) => (
                <g key={v}>
                  <line x1={LEFT} x2={LEFT + geom.plotW} y1={geom.y(v)} y2={geom.y(v)} className="stroke-grid" strokeWidth={1} />
                  <text x={LEFT - 8} y={geom.y(v) + 4} textAnchor="end" className="fill-muted text-[11px] tabular-nums">
                    {formatValue(v)}
                  </text>
                </g>
              ))}
              <line x1={LEFT} x2={LEFT + geom.plotW} y1={geom.y(yMin)} y2={geom.y(yMin)} className="stroke-axis" strokeWidth={1} />

              {xTicks(points[0].t, last.t, geom.plotW).map((t) => (
                <text key={t.getTime()} x={geom.x(t)} y={TOP + plotHeight + 16} textAnchor="middle" className="fill-muted text-[11px]">
                  {format(t, t.getHours() === 0 ? 'EEE' : 'ha')}
                </text>
              ))}

              {placedRefs.map((r) => (
                <g key={r.label}>
                  <line
                    x1={LEFT}
                    x2={LEFT + geom.plotW}
                    y1={geom.y(r.value)}
                    y2={geom.y(r.value)}
                    className={r.tone === 'critical' ? 'stroke-status-critical' : 'stroke-status-warning'}
                    strokeWidth={1}
                  />
                  <text x={LEFT + 4} y={geom.y(r.value) + (r.below ? 12 : -4)} className="fill-ink-2 text-[11px]">
                    {r.label}
                  </text>
                </g>
              ))}

              <path d={geom.area} className="fill-accent/10" />
              <path d={geom.line} fill="none" className="stroke-accent" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />

              <circle cx={geom.x(last.t)} cy={geom.y(last.v)} r={4} className="fill-accent stroke-surface" strokeWidth={2} />
              {endLabel && (
                <text x={geom.x(last.t) + 8} y={geom.y(last.v) + 4} className="fill-ink text-xs font-semibold">
                  {formatValue(last.v)}
                </text>
              )}

              {shown && (
                <g pointerEvents="none">
                  <line x1={geom.x(shown.t)} x2={geom.x(shown.t)} y1={TOP} y2={TOP + plotHeight} className="stroke-axis" strokeWidth={1} />
                  <circle cx={geom.x(shown.t)} cy={geom.y(shown.v)} r={4} className="fill-accent stroke-surface" strokeWidth={2} />
                </g>
              )}
            </svg>

            {shown && (
              <div
                className="pointer-events-none absolute top-0 rounded-lg border border-line/10 bg-surface px-2.5 py-1.5 shadow-md"
                style={{ left: Math.min(Math.max(geom.x(shown.t) - 60, 0), width - 120), width: 120 }}
              >
                <div className="text-sm font-semibold text-ink">{formatValue(shown.v)}</div>
                <div className="text-[11px] text-ink-2">{format(shown.t, 'EEE MMM d, h:mm a')}</div>
              </div>
            )}
          </>
        )
      )}
    </div>
  )
}
