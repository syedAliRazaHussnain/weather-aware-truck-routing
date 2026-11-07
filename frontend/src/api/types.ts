// The API contract, mirroring backend/planner/service.py and views.py.
// Coordinates inside GeoJSON are [lon, lat]; everywhere else they are named lat/lon.

/** Risk levels: 0 Low, 1 Moderate, 2 High, 3 Severe, 4 No Travel. null = weather unknown. */
export type Level = 0 | 1 | 2 | 3 | 4

export interface Place {
  label: string
  lat: number
  lon: number
}

export interface PlanRequest {
  origin: Place
  destination: Place
  /** The origin's local time, no zone: "2026-11-08T08:00" (#7). */
  departure: string
  /** Cargo load in lb; kg is converted before sending (#2). */
  load_lb: number
  interval_mi: 10 | 25 | 50
}

/** A button the UI shows to help fix or retry a problem (#59). */
export type Action =
  | { type: 'retry'; label: string; retry_after_s?: number }
  | { type: 'set_departure'; label: string; value: string }
  | { type: 'set_interval'; label: string; value: 10 | 25 | 50 }
  | { type: 'use_place'; label: string; field: 'origin' | 'destination'; place: Place }
  | { type: 'edit_field'; label: string; field: 'origin' | 'destination' | 'load' }

export interface Problem {
  error: string
  message: string
  actions: Action[]
  /** Only for bad input: which form fields need fixing. */
  fields?: Record<string, unknown>
}

export interface CheckpointWeather {
  wind_mph: number
  gust_mph: number
  rain_in_hr: number
  snow_in_hr: number
}

export interface Checkpoint {
  mile: number
  lat: number
  lon: number
  /** Local time with offset, e.g. "2026-11-08T08:31-07:00". */
  eta: string
  level: Level | null
  label: string
  drivers: ('wind' | 'rain' | 'snow')[]
  load_escalated: boolean
  wind_before_load: string | null
  weather: CheckpointWeather | null
}

export interface RouteSummary {
  severe_mi: number
  high_mi: number
  no_travel_mi: number
  avg_risk: number
}

export interface SegmentProperties {
  level: Level | null
  from_mi: number
  to_mi: number
}

export interface RouteResult {
  /** "A" is the fastest (#60). */
  id: 'A' | 'B' | 'C'
  rank: number | null
  distance_mi: number
  duration_s: number
  summary: RouteSummary | null
  segments: GeoJSON.FeatureCollection<GeoJSON.LineString, SegmentProperties>
  checkpoints: Checkpoint[]
}

/** h0 ... h48: the square's risk level for each slider hour. */
export type HourlyLevels = Record<`h${number}`, Level>

export interface Heatmap {
  start: string
  hours: number
  square_mi: number
  cells: GeoJSON.FeatureCollection<GeoJSON.Polygon, HourlyLevels>
}

export interface Warning {
  message: string
  advice: string
  actions: Action[]
}

export interface PlanResult {
  timezone: string
  departure: string
  weather_status: 'ok' | 'unavailable'
  recommended: RouteResult['id'] | null
  reason: string | null
  warning: Warning | null
  /** A partial result's problem, e.g. weather unavailable (#39). */
  problem: Problem | null
  notes: string[]
  routes: RouteResult[]
  heatmap: Heatmap | null
}
