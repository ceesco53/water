import { formatDistanceToNow } from 'date-fns'
import { CircleCheck, CloudLightning, CloudRain, RefreshCw, Thermometer, Waves } from 'lucide-react'
import clsx from 'clsx'
import type { LucideIcon } from 'lucide-react'
import type { Conditions } from '../types'
import { LEVEL, STATUS, VERDICT } from '../status'
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

/**
 * The headline number: the chance a sample today would exceed the swim
 * standard, as a ring from 0 to twice the Caution line, with a tick at the line.
 */
function ChanceDial({ probability, line, stroke }: { probability: number; line: number; stroke: string }) {
  const r = 62
  const c = 2 * Math.PI * r
  const max = Math.max(line * 2, probability * 1.15)
  const tick = (line / max) * 2 * Math.PI - Math.PI / 2
  return (
    <svg
      viewBox="0 0 160 160"
      className="h-40 w-40 sm:h-48 sm:w-48"
      role="img"
      aria-label={`${chance(probability)} chance bacteria exceed the swim standard today; Caution starts at ${(line * 100).toFixed(1)}%`}
    >
      <circle cx="80" cy="80" r={r} fill="none" stroke="rgb(255 255 255 / 0.14)" strokeWidth="10" />
      <circle
        cx="80"
        cy="80"
        r={r}
        fill="none"
        stroke={stroke}
        strokeWidth="10"
        strokeLinecap="round"
        strokeDasharray={`${Math.max(0.01, probability / max) * c} ${c}`}
        transform="rotate(-90 80 80)"
        style={{ transition: 'stroke-dasharray 900ms cubic-bezier(.2,.8,.2,1)' }}
      />
      {/* Caution line */}
      <line
        x1={80 + (r - 9) * Math.cos(tick)}
        y1={80 + (r - 9) * Math.sin(tick)}
        x2={80 + (r + 9) * Math.cos(tick)}
        y2={80 + (r + 9) * Math.sin(tick)}
        stroke="white"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      <text x="80" y="82" textAnchor="middle" className="fill-white" style={{ fontSize: 46, fontWeight: 600 }}>
        {chance(probability)}
      </text>
      <text x="80" y="102" textAnchor="middle" style={{ fontSize: 11, fill: 'rgb(255 255 255 / 0.75)' }}>
        chance of unsafe
      </text>
      <text x="80" y="116" textAnchor="middle" style={{ fontSize: 11, fill: 'rgb(255 255 255 / 0.75)' }}>
        bacteria today
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

function lowerFirst(text: string): string {
  return text.charAt(0).toLowerCase() + text.slice(1)
}

export function Hero({ data, refreshing, onRefresh }: Props) {
  const verdict = data ? VERDICT[data.verdict] : null
  const risk = data?.bacteria_risk ?? null
  // The findings that set a Caution or Stay-out verdict share its name
  const decisive = data ? data.findings.filter((f) => f.level === data.verdict) : []
  const notes = data ? data.findings.filter((f) => f.level === 'note') : []
  const hazards = data ? data.findings.filter((f) => f.group === 'hazard' && f.level !== 'clear') : []
  const great = data?.verdict === 'good' && notes.length === 0 && risk != null && risk.probability < risk.caution_probability / 3
  const headline = verdict ? (great ? 'Great day for a swim' : verdict.headline) : 'Reading the river…'
  const summary = !data
    ? null
    : data.verdict !== 'good'
    ? `Because: ${decisive.map((f) => lowerFirst(f.reason)).join('; ')}.`
    : notes.length > 0
    ? `Worth knowing: ${notes.map((f) => lowerFirst(f.reason)).join('; ')}.`
    : 'Nothing of concern in the water or the weather right now.'
  const rain72 = data?.weather.radar_rain_72h_in ?? data?.weather.rain_72h_in ?? null
  const riverBend = data?.water_levels.find((g) => g.position === 'your stretch') ?? null
  const StatusIcon = verdict ? STATUS[verdict.status].icon : null
  const dialStroke = risk && risk.probability >= risk.caution_probability ? 'rgb(var(--warning))' : 'rgb(var(--good))'

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
            <h1 className="mt-3 text-4xl font-semibold leading-[1.1] tracking-tight sm:text-5xl">{headline}</h1>
            {summary && <p className="mt-4 text-base text-white/80 sm:text-lg">{summary}</p>}

            {data && (
              <ul className="mt-5 flex flex-wrap gap-2" aria-label="Weather and safety">
                {hazards.length === 0 ? (
                  <li className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-sm ring-1 ring-inset ring-white/15">
                    <CircleCheck className="h-4 w-4" style={{ color: 'rgb(var(--good))' }} aria-hidden />
                    No weather hazards
                  </li>
                ) : (
                  hazards.map((f) => {
                    const Icon = STATUS[LEVEL[f.level].status].icon
                    const color = f.level === 'avoid' ? 'rgb(var(--critical))' : f.level === 'caution' ? 'rgb(var(--warning))' : 'white'
                    return (
                      <li
                        key={f.key}
                        title={f.reason}
                        className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-sm ring-1 ring-inset ring-white/15"
                      >
                        <Icon className="h-4 w-4" style={{ color }} aria-hidden />
                        {f.label}
                        <span className="text-white/60">· {LEVEL[f.level].label}</span>
                      </li>
                    )
                  })
                )}
              </ul>
            )}

            {data && (
              <div className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Glance
                  icon={Thermometer}
                  label="Water"
                  value={data.water.temp_f != null ? `${Math.round(data.water.temp_f)}°F` : '—'}
                />
                <Glance icon={CloudRain} label="Rain, 72h" value={rain72 != null ? `${rain72.toFixed(2)}"` : '—'} />
                <Glance
                  icon={Waves}
                  label="River level"
                  value={riverBend ? `${riverBend.latest_ft.toFixed(1)} ft` : '—'}
                />
                <Glance
                  icon={CloudLightning}
                  label="Thunder, 6h"
                  value={data.weather.thunder_pct_6h != null ? `${data.weather.thunder_pct_6h}%` : '—'}
                />
              </div>
            )}
          </div>

          {data && verdict && StatusIcon && (
            <div className="flex flex-col items-center gap-3 justify-self-center lg:justify-self-end">
              {risk ? (
                <ChanceDial probability={risk.probability} line={risk.caution_probability} stroke={dialStroke} />
              ) : (
                <div className="grid h-40 w-40 place-items-center rounded-full ring-[10px] ring-white/15 text-center text-sm text-white/70 sm:h-48 sm:w-48">
                  Bacteria risk unavailable
                </div>
              )}
              <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1 text-sm font-medium ring-1 ring-inset ring-white/20">
                <StatusIcon className="h-4 w-4" style={{ color: verdict.stroke }} aria-hidden />
                {verdict.label}
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
