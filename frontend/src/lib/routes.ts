// Small calculations on a planned route, for the route cards and the map.

import type { Level, RouteResult } from '../api/types'

export interface LevelShare {
  level: Level | null
  miles: number
}

/** Miles of a route at each risk level, in route order, for the card's risk bar. */
export function milesByLevel(route: RouteResult): LevelShare[] {
  return route.segments.features.map((f) => ({
    level: f.properties.level,
    miles: f.properties.to_mi - f.properties.from_mi,
  }))
}

/** How much slower a route is than the fastest one, in seconds (0 for the fastest). */
export function extraTime(route: RouteResult, routes: RouteResult[]): number {
  return route.duration_s - Math.min(...routes.map((r) => r.duration_s))
}

/** [west, south, east, north] around every route, for fitting the map to a plan. */
export function bounds(routes: RouteResult[]): [number, number, number, number] {
  let west = 180
  let south = 90
  let east = -180
  let north = -90
  for (const route of routes) {
    for (const feature of route.segments.features) {
      for (const [lon, lat] of feature.geometry.coordinates) {
        west = Math.min(west, lon)
        east = Math.max(east, lon)
        south = Math.min(south, lat)
        north = Math.max(north, lat)
      }
    }
  }
  return [west, south, east, north]
}
