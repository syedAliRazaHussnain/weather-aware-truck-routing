// Every failure becomes a plain Problem with actions (#59).
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiProblem, OFFLINE, UNEXPECTED, planTrip, searchPlaces } from './client'
import type { PlanRequest } from './types'

const TRIP: PlanRequest = {
  origin: { label: 'Denver', lat: 39.74, lon: -104.99 },
  destination: { label: 'Salt Lake City', lat: 40.76, lon: -111.89 },
  departure: '2026-11-08T08:00',
  load_lb: 42000,
  interval_mi: 25,
}

function answer(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: () => (body instanceof Error ? Promise.reject(body) : Promise.resolve(body)),
  })
}

async function problemFrom(promise: Promise<unknown>): Promise<ApiProblem> {
  try {
    await promise
  } catch (error) {
    if (error instanceof ApiProblem) return error
    throw error
  }
  throw new Error('expected an ApiProblem')
}

afterEach(() => vi.unstubAllGlobals())

describe('api client', () => {
  it('posts the trip as JSON and returns the plan', async () => {
    const fetch = answer(200, { recommended: 'A' })
    vi.stubGlobal('fetch', fetch)
    expect(await planTrip(TRIP)).toEqual({ recommended: 'A' })
    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe('/api/plan')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual(TRIP)
  })

  it("keeps the server's own problem, message and buttons", async () => {
    const problem = {
      error: 'departure_passed',
      message: 'That departure time has passed.',
      actions: [{ type: 'set_departure', label: 'Leave now', value: '2026-11-08T09:00' }],
    }
    vi.stubGlobal('fetch', answer(400, problem))
    const caught = await problemFrom(planTrip(TRIP))
    expect(caught.problem).toEqual(problem)
    expect(caught.status).toBe(400)
  })

  it('turns no network into the offline problem', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    expect((await problemFrom(planTrip(TRIP))).problem).toEqual(OFFLINE)
  })

  it('turns a non-JSON error page into a friendly server error', async () => {
    vi.stubGlobal('fetch', answer(502, new SyntaxError('Unexpected token <')))
    expect((await problemFrom(planTrip(TRIP))).problem).toEqual(UNEXPECTED)
  })

  it('lets a cancelled request stay cancelled', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new DOMException('aborted', 'AbortError')))
    await expect(planTrip(TRIP)).rejects.toThrow('aborted')
  })

  it('searches places near the map view (#4)', async () => {
    const fetch = answer(200, [])
    vi.stubGlobal('fetch', fetch)
    await searchPlaces('salt lake', { lat: 39.7392, lon: -104.9903 })
    expect(fetch.mock.calls[0][0]).toBe('/api/places?q=salt+lake&lat=39.739&lon=-104.990')
  })
})
