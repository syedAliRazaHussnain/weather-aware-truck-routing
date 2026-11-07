// Talks to the Django API. Every failure, including no network, becomes a Problem
// with a plain message and actions, so the UI never shows a raw error (#59).

import type { Place, PlanRequest, PlanResult, Problem } from './types'

/** Empty in development (Vite proxies /api); the Render URL in production. */
const API_BASE = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')

/** A Problem thrown by the client, with the HTTP status when there was one. */
export class ApiProblem extends Error {
  readonly problem: Problem
  readonly status: number | null

  constructor(problem: Problem, status: number | null) {
    super(problem.message)
    this.problem = problem
    this.status = status
  }
}

export const OFFLINE: Problem = {
  error: 'offline',
  message: "You're offline. Your trip details are kept.",
  actions: [{ type: 'retry', label: 'Try again' }],
}

export const UNEXPECTED: Problem = {
  error: 'server_error',
  message: 'Something went wrong on our side. Your trip details are kept.',
  actions: [{ type: 'retry', label: 'Try again' }],
}

/** True when a value looks like the API's {error, message, actions} shape. */
export function isProblem(value: unknown): value is Problem {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as Problem).error === 'string' &&
    typeof (value as Problem).message === 'string' &&
    Array.isArray((value as Problem).actions)
  )
}

/** One API call: JSON in, JSON out, or an ApiProblem. Aborts are passed through. */
export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(API_BASE + path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init.headers },
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiProblem(OFFLINE, null)
  }
  let body: unknown
  try {
    body = await response.json()
  } catch {
    throw new ApiProblem(UNEXPECTED, response.status)
  }
  if (!response.ok) {
    throw new ApiProblem(isProblem(body) ? body : UNEXPECTED, response.status)
  }
  return body as T
}

/** Plan a trip (POST /api/plan). */
export function planTrip(trip: PlanRequest, signal?: AbortSignal): Promise<PlanResult> {
  return request<PlanResult>('/api/plan', { method: 'POST', body: JSON.stringify(trip), signal })
}

/** Place suggestions for what the driver is typing, near the map view (#4). */
export function searchPlaces(
  text: string,
  focus?: { lat: number; lon: number },
  signal?: AbortSignal,
): Promise<Place[]> {
  const params = new URLSearchParams({ q: text })
  if (focus) {
    params.set('lat', focus.lat.toFixed(3))
    params.set('lon', focus.lon.toFixed(3))
  }
  return request<Place[]>(`/api/places?${params}`, { signal })
}

/** Wake the free server as soon as the page opens; failures are ignored (#58). */
export function wakeServer(): void {
  fetch(API_BASE + '/api/health').catch(() => undefined)
}
