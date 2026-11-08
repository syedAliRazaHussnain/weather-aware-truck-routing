// The recommendation, its reason, warnings and notes, and a card per route.
import { useEffect, useRef } from 'react'
import type { Action, PlanResult } from '../api/types'
import { ActionButton } from './ProblemPanel'
import { RouteCard } from './RouteCard'

interface Props {
  plan: PlanResult
  selectedId: string | null
  onSelect: (id: PlanResult['routes'][number]['id']) => void
  onAction: (action: Action) => void
}

export function ResultsPanel({ plan, selectedId, onSelect, onAction }: Props) {
  const routes = [...plan.routes].sort((a, b) => (a.rank ?? 9) - (b.rank ?? 9))
  const section = useRef<HTMLElement>(null)

  // On a phone the results sit below the form, so bring a new plan into view.
  useEffect(() => {
    if (window.matchMedia('(max-width: 800px)').matches) {
      section.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [plan])

  return (
    <section className="results" aria-label="Trip results" ref={section}>
      {plan.recommended && (
        <div className="recommendation">
          <h2>Take Route {plan.recommended}</h2>
          {plan.reason && <p>{plan.reason}</p>}
        </div>
      )}
      {plan.warning && (
        <div className="warning" role="alert">
          <p>
            <strong>{plan.warning.message}</strong> {plan.warning.advice}
          </p>
          <div className="actions">
            {plan.warning.actions.map((action) => (
              <ActionButton key={action.label} action={action} onAction={onAction} />
            ))}
          </div>
        </div>
      )}
      <div className="route-list">
        {routes.map((route) => (
          <RouteCard
            key={route.id}
            route={route}
            routes={plan.routes}
            recommended={route.id === plan.recommended}
            selected={route.id === selectedId}
            onSelect={() => onSelect(route.id)}
          />
        ))}
      </div>
      {plan.notes.length > 0 && (
        <ul className="notes">
          {plan.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
    </section>
  )
}
