import clsx from 'clsx'
import type { RatingColor, ScoreFactor } from '../types'

interface Props {
  score: number
  rating: string
  color: RatingColor
  factors: ScoreFactor[]
}

const colorMap: Record<RatingColor, { ring: string; text: string; bg: string; badge: string }> = {
  green: {
    ring: 'ring-green-500',
    text: 'text-green-400',
    bg: 'from-green-900/30 to-surface-card',
    badge: 'bg-green-500/20 text-green-300 border-green-500/30',
  },
  blue: {
    ring: 'ring-blue-500',
    text: 'text-blue-400',
    bg: 'from-blue-900/30 to-surface-card',
    badge: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  },
  yellow: {
    ring: 'ring-yellow-500',
    text: 'text-yellow-400',
    bg: 'from-yellow-900/30 to-surface-card',
    badge: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30',
  },
  red: {
    ring: 'ring-red-500',
    text: 'text-red-400',
    bg: 'from-red-900/30 to-surface-card',
    badge: 'bg-red-500/20 text-red-300 border-red-500/30',
  },
}

const impactColor = (impact: number) => {
  if (impact < -15) return 'text-red-400'
  if (impact < 0) return 'text-yellow-400'
  return 'text-green-400'
}

export function ScoreCard({ score, rating, color, factors }: Props) {
  const c = colorMap[color]

  return (
    <div className={clsx('rounded-2xl bg-gradient-to-br p-6 border border-surface-border', c.bg)}>
      <div className="flex flex-col sm:flex-row items-center gap-6">
        {/* Score dial */}
        <div className={clsx(
          'flex-shrink-0 w-36 h-36 rounded-full ring-4 flex flex-col items-center justify-center',
          'bg-surface-card', c.ring
        )}>
          <span className={clsx('text-5xl font-bold tabular-nums', c.text)}>{score}</span>
          <span className="text-xs text-slate-400 mt-1">/ 100</span>
        </div>

        {/* Rating + factors */}
        <div className="flex-1 w-full">
          <div className="flex items-center gap-3 mb-4">
            <span className={clsx('text-2xl font-bold', c.text)}>{rating}</span>
            <span className={clsx('text-xs px-2 py-1 rounded-full border font-medium', c.badge)}>
              TODAY
            </span>
          </div>

          <div className="space-y-2">
            {factors.map((f) => (
              <div key={f.label} className="flex items-start gap-3 text-sm">
                <span className={clsx('font-mono font-bold w-10 text-right flex-shrink-0 tabular-nums', impactColor(f.impact))}>
                  {f.impact === 0 ? '+0' : f.impact}
                </span>
                <div className="min-w-0">
                  <span className="text-slate-300 font-medium">{f.label}</span>
                  <span className="text-slate-500 ml-2">{f.reason}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Score legend */}
      <div className="mt-5 pt-4 border-t border-surface-border grid grid-cols-4 gap-2 text-center text-xs">
        {[
          { label: 'Excellent', range: '85–100', c: 'text-green-400' },
          { label: 'Good', range: '70–84', c: 'text-blue-400' },
          { label: 'Caution', range: '50–69', c: 'text-yellow-400' },
          { label: 'Avoid', range: '<50', c: 'text-red-400' },
        ].map((tier) => (
          <div key={tier.label}>
            <div className={clsx('font-semibold', tier.c)}>{tier.label}</div>
            <div className="text-slate-500">{tier.range}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
