// A problem as a plain message plus buttons that help fix it (#59).
import { useEffect, useState } from 'react'
import type { Action, Problem } from '../api/types'

interface Props {
  problem: Problem
  onAction: (action: Action) => void
}

export function ProblemPanel({ problem, onAction }: Props) {
  return (
    <div className="problem" role="alert">
      <p>{problem.message}</p>
      {problem.actions.length > 0 && (
        <div className="actions">
          {problem.actions.map((action) => (
            <ActionButton key={`${action.type}-${action.label}`} action={action} onAction={onAction} />
          ))}
        </div>
      )}
    </div>
  )
}

/** One button; a retry with a countdown waits, then retries by itself. */
export function ActionButton({ action, onAction }: { action: Action; onAction: (action: Action) => void }) {
  const wait = action.type === 'retry' ? (action.retry_after_s ?? 0) : 0
  const [left, setLeft] = useState(wait)

  useEffect(() => {
    if (left <= 0) return
    const timer = setTimeout(() => {
      if (left === 1) onAction(action)
      setLeft(left - 1)
    }, 1000)
    return () => clearTimeout(timer)
  }, [left, action, onAction])

  return (
    <button type="button" onClick={() => onAction(action)}>
      {left > 0 ? `${action.label} (retrying in ${left} s)` : action.label}
    </button>
  )
}
