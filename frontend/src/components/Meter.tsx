import clsx from 'clsx'

interface Props {
  value: number
  max: number
  // A marked threshold on the track, e.g. the Caution line
  threshold?: number
  thresholdLabel?: string
  // Fill color class; the track is a lighter step of the same accent
  fillClass?: string
  label: string
}

/** A single value against a limit: same-ramp track, fill, and a threshold tick. */
export function Meter({ value, max, threshold, thresholdLabel, fillClass = 'bg-accent', label }: Props) {
  const pct = (v: number) => `${Math.max(0, Math.min(100, (v / max) * 100))}%`
  return (
    <div className="space-y-1.5">
      <div
        className="relative h-2 rounded-full bg-accent-soft"
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={value}
      >
        <div className={clsx('absolute inset-y-0 left-0 rounded-full', fillClass)} style={{ width: pct(value) }} />
        {threshold != null && (
          <div
            className="absolute -top-1 -bottom-1 w-0.5 rounded-full bg-ink"
            style={{ left: pct(threshold) }}
            aria-hidden
          />
        )}
      </div>
      {thresholdLabel && threshold != null && (
        <div className="relative h-4 text-[11px] text-muted">
          <span
            className="absolute -translate-x-1/2 whitespace-nowrap"
            style={{ left: `clamp(2.5rem, ${pct(threshold)}, calc(100% - 2.5rem))` }}
          >
            {thresholdLabel}
          </span>
        </div>
      )}
    </div>
  )
}
