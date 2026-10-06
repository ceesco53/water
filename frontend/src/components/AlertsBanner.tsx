import clsx from 'clsx'
import { format, parseISO } from 'date-fns'
import type { NwsAlert } from '../types'

export function AlertsBanner({ alerts }: { alerts: NwsAlert[] }) {
  if (alerts.length === 0) return null

  return (
    <div className="space-y-2">
      {alerts.map((alert, i) => {
        const severe = alert.severity === 'Extreme' || alert.severity === 'Severe'
        return (
          <div
            key={`${alert.event}-${i}`}
            className={clsx(
              'rounded-xl border p-3 flex items-start gap-3 text-sm',
              severe
                ? 'border-red-500/40 bg-red-900/20 text-red-200'
                : 'border-yellow-500/40 bg-yellow-900/10 text-yellow-200'
            )}
          >
            <span className="text-lg">⚠️</span>
            <div className="min-w-0">
              <div className="font-semibold">
                {alert.event}
                {alert.ends && (
                  <span className="font-normal text-xs opacity-75">
                    {' '}· until {format(parseISO(alert.ends), 'EEE h:mm a')}
                  </span>
                )}
              </div>
              {alert.headline && <div className="text-xs opacity-75 mt-0.5">{alert.headline}</div>}
            </div>
          </div>
        )
      })}
    </div>
  )
}
