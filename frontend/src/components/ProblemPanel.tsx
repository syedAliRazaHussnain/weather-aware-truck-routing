// A problem as a plain message plus buttons that help fix it (#59).
import { useEffect, useState } from 'react'
import type { Action, Problem } from '../api/types'

interface Props {
  problem: Problem
  onAction: (action: Action) => void
  /** Retry by itself after a countdown; only once in a row, so a busy service isn't hammered. */
  autoRetry?: boolean
  onAutoRetry?: () => void
}

export function ProblemPanel({ problem, onAction, autoRetry = false, onAutoRetry }: Props) {
  return (
    <div className="problem" role="alert">
      <p>{problem.message}</p>
      {problem.actions.length > 0 && (
        <div className="actions">
          {problem.actions.map((action) => (
            <ActionButton
              key={`${action.type}-${action.label}`}
              action={action}
              onAction={onAction}
              autoRetry={autoRetry}
              onAutoRetry={onAutoRetry}
            />
          ))}
        </div>
      )}
    </div>
  )
}

interface ButtonProps {
  action: Action
  onAction: (action: Action) => void
  autoRetry?: boolean
  onAutoRetry?: () => void
}

/** One button; a retry with a countdown waits, then retries by itself (if allowed). */
export function ActionButton({ action, onAction, autoRetry = false, onAutoRetry }: ButtonProps) {
  const wait = autoRetry && action.type === 'retry' ? (action.retry_after_s ?? 0) : 0
  const [left, setLeft] = useState(wait)

  useEffect(() => {
    if (left <= 0) return
    const timer = setTimeout(() => {
      if (left === 1) {
        onAutoRetry?.()
        onAction(action)
      }
      setLeft(left - 1)
    }, 1000)
    return () => clearTimeout(timer)
  }, [left, action, onAction, onAutoRetry])

  return (
    <button type="button" onClick={() => onAction(action)}>
      {left > 0 ? `${action.label} (retrying in ${left} s)` : action.label}
    </button>
  )
}
