// Plans a trip and keeps the latest result or problem. A newer plan cancels an older one.
import { useCallback, useRef, useState } from 'react'
import { ApiProblem, UNEXPECTED, planTrip } from '../api/client'
import type { PlanRequest, PlanResult, Problem } from '../api/types'

const SLOW_AFTER_MS = 6000 // #58: after this, say the free server may be waking up

export function usePlan() {
  const [plan, setPlan] = useState<PlanResult | null>(null)
  const [problem, setProblem] = useState<Problem | null>(null)
  const [loading, setLoading] = useState(false)
  const [slow, setSlow] = useState(false)
  const current = useRef<AbortController | null>(null)

  const run = useCallback(async (request: PlanRequest) => {
    current.current?.abort()
    const controller = new AbortController()
    current.current = controller
    setLoading(true)
    setSlow(false)
    setProblem(null)
    const timer = setTimeout(() => setSlow(true), SLOW_AFTER_MS)
    try {
      const result = await planTrip(request, controller.signal)
      setPlan(result)
      setProblem(result.problem) // e.g. weather unknown: routes still shown (#39)
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return
      setPlan(null) // an old plan for a different trip would be misleading
      setProblem(error instanceof ApiProblem ? error.problem : UNEXPECTED)
    } finally {
      clearTimeout(timer)
      if (current.current === controller) {
        setLoading(false)
        setSlow(false)
      }
    }
  }, [])

  return { plan, problem, loading, slow, run }
}
