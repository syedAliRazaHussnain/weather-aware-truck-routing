// Place suggestions as the driver types: waits for a pause, cancels stale searches.
import { useEffect, useState } from 'react'
import { searchPlaces } from '../api/client'
import type { Place } from '../api/types'

const PAUSE_MS = 250

export function usePlaceSearch(text: string, focus: { lat: number; lon: number } | undefined, enabled: boolean) {
  const [results, setResults] = useState<Place[]>([])
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!enabled || text.trim().length < 2) {
      setResults([])
      return
    }
    const controller = new AbortController()
    const timer = setTimeout(() => {
      searchPlaces(text.trim(), focus, controller.signal)
        .then((places) => {
          setResults(places)
          setFailed(false)
        })
        .catch((error) => {
          if (error instanceof DOMException && error.name === 'AbortError') return
          setResults([])
          setFailed(true)
        })
    }, PAUSE_MS)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
    // Focus only biases ranking; re-searching on every map move would waste quota.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, enabled])

  return { results, failed }
}
