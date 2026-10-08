import { formatDistanceToNow } from 'date-fns'
import { CloudLightning, CloudRain, FlaskConical, RefreshCw, Thermometer, Waves } from 'lucide-react'
import clsx from 'clsx'
import type { LucideIcon } from 'lucide-react'
import type { Conditions } from '../types'
import { RATING, STATUS } from '../status'
import { ThemeToggle } from './ThemeToggle'

interface Props {
  data: Conditions | null
  refreshing: boolean
  onRefresh: () => void
}

// One sine period is 1440 wide; each path holds two, so sliding it left by
// half its width loops seamlessly.
function wavePath(amplitude: number, baseline: number): string {
  const segs = [0, 1, 2, 3]
    .map((i) => {
      const x = i * 720
      const dir = i % 2 === 0 ? 1 : -1
      return `C${x + 240},${baseline + dir * amplitude} ${x + 480},${baseline - dir * amplitude} ${x + 720},${baseline}`
    })
    .join(' ')
  return `M0,${baseline} ${segs} L2880,160 L0,160 Z`
}

const WAVES = [
  { d: wavePath(18, 70), fill: 'rgb(255 255 255 / 0.06)', duration: '38s' },
  { d: wavePath(14, 88), fill: 'rgb(255 255 255 / 0.09)', duration: '27s' },
  { d: wavePath(10, 110), fill: 'rgb(var(--page))', duration: '19s' },
]

function ScoreDial({ score, stroke }: { score: number; stroke: string }) {
  const r = 62
  const c = 2 * Math.PI * r
  return (
    <svg viewBox="0 0 160 160" className="h-40 w-40 sm:h-48 sm:w-48" role="img" aria-label={`Swim score ${score} out of 100`}>
      <circle cx="80" cy="80" r={r} fill="none" stroke="rgb(255 255 255 / 0.14)" strokeWidth="10" />
      <circle
        cx="80"
        cy="80"
        r={r}
        fill="none"
        stroke={stroke}
        strokeWidth="10"
        strokeLinecap="round"
        strokeDasharray={`${(score / 100) * c} ${c}`}
        transform="rotate(-90 80 80)"
        style={{ transition: 'stroke-dasharray 900ms cubic-bezier(.2,.8,.2,1)' }}
      />
      <text x="80" y="84" textAnchor="middle" className="fill-white" style={{ fontSize: 52, fontWeight: 600 }}>
        {score}
      </text>
      <text x="80" y="110" textAnchor="middle" style={{ fontSize: 12, fill: 'rgb(255 255 255 / 0.7)' }}>
        out of 100
      </text>
    </svg>
  )
}

function Glance({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string }) {
  return (
    <div className="rounded-xl bg-white/[0.08] px-3.5 py-3 ring-1 ring-inset ring-white/10 backdrop-blur-sm">
      <div className="flex items-center gap-1.5 text-xs text-white/70">
        <Icon className="h-3.5 w-3.5" aria-hidden />
        {label}
      </div>
      <div className="mt-1 text-lg font-semibold text-white">{value}</div>
    </div>
  )
}

function chance(p: number): string {
  return p < 0.01 ? '<1%' : `${Math.round(p * 100)}%`
}

export function Hero({ data, refreshing, onRefresh }: Props) {
  const rating = data ? RATING[data.rating] ?? RATING.Good : null
  const holdingBack = data
    ? [...data.score_factors].filter((f) => f.impact < 0).sort((a, b) => a.impact - b.impact).slice(0, 2)
    : []
  const rain72 = data?.weather.radar_rain_72h_in ?? data?.weather.rain_72h_in ?? null
  const StatusIcon = rating ? STATUS[rating.status].icon : null

  return (
    <section className="relative isolate overflow-hidden bg-gradient-to-br from-[#0d366b] via-[#1c5cab] to-[#2a78d6] text-white">
      {/* Soft light at the top-right, like sun on the water */}
      <div
        className="pointer-events-none absolute -right-32 -top-40 h-[28rem] w-[28rem] rounded-full bg-[#86b6ef]/25 blur-3xl"
        aria-hidden
      />

      <div className="relative mx-auto max-w-6xl px-4 sm:px-6">
        <nav className="flex items-center justify-between py-4">
          <div className="flex items-center gap-2.5">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-white/15 ring-1 ring-inset ring-white/20">
              <Waves className="h-5 w-5" aria-hidden />
            </span>
            <div className="leading-tight">
              <div className="text-[15px] font-semibold">River Bend Water</div>
              <div className="text-xs text-white/70">Trent River · River Bend, NC</div>
            </div>
          </div>
          <div className="flex items-center gap-1 sm:gap-2">
            {data && (
              <span className="hidden text-xs text-white/70 sm:block">
                Updated {formatDistanceToNow(new Date(data.last_updated), { addSuffix: true })}
              </span>
            )}
            <ThemeToggle />
            <button
              type="button"
              onClick={onRefresh}
              disabled={refreshing}
              className="inline-flex h-9 items-center gap-1.5 rounded-full bg-white/10 px-3.5 text-xs font-medium ring-1 ring-inset ring-white/20 transition hover:bg-white/20 disabled:opacity-60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white"
            >
              <RefreshCw className={clsx('h-3.5 w-3.5', refreshing && 'animate-spin')} aria-hidden />
              {refreshing ? 'Refreshing' : 'Refresh'}
            </button>
          </div>
        </nav>

        <div className="grid items-center gap-8 pb-28 pt-6 sm:pt-10 lg:grid-cols-[1fr_auto] lg:pb-36">
          <div className="max-w-2xl">
            <p className="text-sm font-medium uppercase tracking-[0.14em] text-white/70">Today on the Trent</p>
            <h1 className="mt-3 text-4xl font-semibold leading-[1.1] tracking-tight sm:text-5xl">
              {rating ? rating.verdict : 'Reading the river…'}
            </h1>
            {data && (
              <p className="mt-4 text-base text-white/80 sm:text-lg">
                {holdingBack.length === 0
                  ? 'Nothing is pulling the score down right now.'
                  : `Holding it back: ${holdingBack.map((f) => `${f.label.toLowerCase()} (−${Math.abs(f.impact)})`).join(' and ')}.`}
              </p>
            )}

            {data && (
              <div className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Glance
                  icon={Thermometer}
                  label="Water"
                  value={data.water.temp_f != null ? `${Math.round(data.water.temp_f)}°F` : '—'}
                />
                <Glance
                  icon={FlaskConical}
                  label="Bacteria risk"
                  value={data.bacteria_risk ? chance(data.bacteria_risk.probability) : '—'}
                />
                <Glance icon={CloudRain} label="Rain, 72h" value={rain72 != null ? `${rain72.toFixed(2)}"` : '—'} />
                <Glance
                  icon={CloudLightning}
                  label="Thunder, 6h"
                  value={data.weather.thunder_pct_6h != null ? `${data.weather.thunder_pct_6h}%` : '—'}
                />
              </div>
            )}
          </div>

          {data && rating && StatusIcon && (
            <div className="flex flex-col items-center gap-3 justify-self-center lg:justify-self-end">
              <ScoreDial score={data.score} stroke={rating.stroke} />
              <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-sm font-medium ring-1 ring-inset ring-white/20">
                <StatusIcon className="h-4 w-4" style={{ color: rating.stroke }} aria-hidden />
                {data.rating}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Waves, the front one in the page color so the hero melts into the page */}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-40 overflow-hidden" aria-hidden>
        {WAVES.map((w) => (
          <svg
            key={w.duration}
            className="wave-layer absolute bottom-0 left-0 h-full w-[200%]"
            style={{ ['--wave-duration' as string]: w.duration }}
            viewBox="0 0 2880 160"
            preserveAspectRatio="none"
          >
            <path d={w.d} fill={w.fill} />
          </svg>
        ))}
      </div>
    </section>
  )
}
