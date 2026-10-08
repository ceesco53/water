import clsx from 'clsx'
import { format, parseISO } from 'date-fns'
import { OctagonAlert, TriangleAlert } from 'lucide-react'
import type { NwsAlert } from '../types'

export function AlertsBanner({ alerts }: { alerts: NwsAlert[] }) {
  if (alerts.length === 0) return null

  return (
    <div className="space-y-2" role="region" aria-label="Active weather alerts">
      {alerts.map((alert, i) => {
        const severe = alert.severity === 'Extreme' || alert.severity === 'Severe'
        const Icon = severe ? OctagonAlert : TriangleAlert
        return (
          <div
            key={`${alert.event}-${i}`}
            className={clsx(
              'card flex items-start gap-3 border-l-4 p-4',
              severe ? 'border-l-status-critical' : 'border-l-status-warning'
            )}
          >
            <Icon
              className={clsx('mt-0.5 h-5 w-5 flex-shrink-0', severe ? 'text-status-critical' : 'text-status-warning')}
              aria-hidden
            />
            <div className="min-w-0">
              <div className="text-sm font-semibold text-ink">
                {alert.event}
                {alert.ends && (
                  <span className="font-normal text-ink-2"> · until {format(parseISO(alert.ends), 'EEE h:mm a')}</span>
                )}
              </div>
              {alert.headline && <p className="mt-0.5 text-sm text-ink-2">{alert.headline}</p>}
            </div>
          </div>
        )
      })}
    </div>
  )
}
