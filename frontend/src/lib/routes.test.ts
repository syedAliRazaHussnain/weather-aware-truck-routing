import { describe, expect, it } from 'vitest'
import type { RouteResult } from '../api/types'
import { bounds, extraTime, milesByLevel } from './routes'

function route(id: 'A' | 'B', duration_s: number, stretches: [number | null, number, number][]): RouteResult {
  return {
    id,
    rank: null,
    distance_mi: stretches.at(-1)?.[2] ?? 0,
    duration_s,
    summary: null,
    checkpoints: [],
    segments: {
      type: 'FeatureCollection',
      features: stretches.map(([level, from, to], i) => ({
        type: 'Feature',
        properties: { level: level as 0 | null, from_mi: from, to_mi: to },
        geometry: { type: 'LineString', coordinates: [[-105 + i, 40], [-104 + i, 41]] },
      })),
    },
  }
}

describe('route helpers', () => {
  it('splits a route into miles per risk level for the card bar', () => {
    const r = route('A', 3600, [[0, 0, 12.5], [3, 12.5, 37.5], [0, 37.5, 50]])
    expect(milesByLevel(r)).toEqual([
      { level: 0, miles: 12.5 },
      { level: 3, miles: 25 },
      { level: 0, miles: 12.5 },
    ])
  })

  it('shows how much slower each route is than the fastest', () => {
    const fast = route('A', 3600, [[0, 0, 10]])
    const slow = route('B', 5400, [[0, 0, 10]])
    expect(extraTime(slow, [fast, slow])).toBe(1800)
    expect(extraTime(fast, [fast, slow])).toBe(0)
  })

  it('finds the box around every route for fitting the map', () => {
    const r = route('A', 3600, [[0, 0, 10], [0, 10, 20]])
    expect(bounds([r])).toEqual([-105, 40, -103, 41])
  })
})
