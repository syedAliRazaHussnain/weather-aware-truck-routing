// One route's summary: time, distance, risky miles and a risk bar along the route.
import type { RouteResult } from '../api/types'
import { levelColor, levelLabel } from '../lib/risk'
import { extraTime, milesByLevel } from '../lib/routes'
import { formatDuration } from '../lib/time'

interface Props {
  route: RouteResult
  routes: RouteResult[]
  recommended: boolean
  selected: boolean
  onSelect: () => void
}

export function RouteCard({ route, routes, recommended, selected, onSelect }: Props) {
  const extra = extraTime(route, routes)
  const s = route.summary
  return (
    <button type="button" className={`route-card${selected ? ' selected' : ''}`} aria-pressed={selected} onClick={onSelect}>
      <div className="route-card-head">
        <span className="route-id">Route {route.id}</span>
        {recommended && <span className="badge">Recommended</span>}
        <span className="route-time">
          {formatDuration(route.duration_s)} · {Math.round(route.distance_mi)} mi
          {extra >= 60 && <span className="muted"> (+{formatDuration(extra)})</span>}
        </span>
      </div>
      <div className="risk-bar" aria-hidden="true">
        {milesByLevel(route).map((share, i) => (
          <span key={i} style={{ flexGrow: share.miles, background: levelColor(share.level) }} title={levelLabel(share.level)} />
        ))}
      </div>
      {s ? (
        <p className="route-stats">
          {s.no_travel_mi > 0 && <strong className="no-travel">No Travel {s.no_travel_mi} mi · </strong>}
          Severe {s.severe_mi} mi · High {s.high_mi} mi · Avg risk {s.avg_risk.toFixed(2)}
        </p>
      ) : (
        <p className="route-stats muted">Weather unknown</p>
      )}
    </button>
  )
}
