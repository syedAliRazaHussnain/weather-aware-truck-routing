// The form's rules and what each problem button does (#5, #10, #59).
import { describe, expect, it } from 'vitest'
import type { Place } from '../api/types'
import { EMPTY_FORM, type TripForm, applyAction, remainingErrors, toPlanRequest } from './form'

const DENVER: Place = { label: 'Denver, CO, USA', lat: 39.74, lon: -104.99 }
const SLC: Place = { label: 'Salt Lake City, UT, USA', lat: 40.76, lon: -111.89 }
const FILLED: TripForm = { ...EMPTY_FORM, origin: DENVER, destination: SLC, load: '42000' }

describe('toPlanRequest', () => {
  it('sends no departure for "Leave now", so the server uses now at the origin (#10)', () => {
    const result = toPlanRequest(FILLED)
    expect(result).toEqual({
      request: { origin: DENVER, destination: SLC, load_lb: 42000, interval_mi: 25 },
    })
  })

  it('sends the chosen local time when leaving later (#7)', () => {
    const result = toPlanRequest({ ...FILLED, leaveNow: false, departure: '2026-11-08T08:00' })
    expect('request' in result && result.request.departure).toBe('2026-11-08T08:00')
  })

  it('converts a kg load to lb (#2)', () => {
    const result = toPlanRequest({ ...FILLED, load: '20000', loadUnit: 'kg' })
    expect('request' in result && result.request.load_lb).toBe(44092)
  })

  it('asks for places picked from suggestions, not just typed (#5)', () => {
    const result = toPlanRequest({ ...FILLED, origin: null })
    expect(result).toEqual({ errors: { origin: 'Pick a starting point from the suggestions.' } })
  })

  it('names every field that needs fixing at once', () => {
    const result = toPlanRequest({ ...EMPTY_FORM, leaveNow: false })
    expect('errors' in result && Object.keys(result.errors).sort()).toEqual([
      'departure',
      'destination',
      'load',
      'origin',
    ])
  })

  it('catches a load with an extra zero (#2)', () => {
    const result = toPlanRequest({ ...FILLED, load: '420000' })
    expect('errors' in result && result.errors.load).toMatch(/extra zero/)
  })
})

describe('applyAction', () => {
  it('Leave now / latest date: sets the departure and plans again', () => {
    const outcome = applyAction(FILLED, {
      type: 'set_departure',
      label: 'Leave now',
      value: '2026-11-08T09:00',
    })
    expect(outcome.form.leaveNow).toBe(false)
    expect(outcome.form.departure).toBe('2026-11-08T09:00')
    expect(outcome.replan).toBe(true)
  })

  it('Use 25 mi: changes only the interval and plans again', () => {
    const outcome = applyAction({ ...FILLED, interval: 10 }, {
      type: 'set_interval',
      label: 'Use 25 mi',
      value: 25,
    })
    expect(outcome.form).toEqual({ ...FILLED, interval: 25 })
    expect(outcome.replan).toBe(true)
  })

  it('Use Rawlins, WY: fills in that field and plans again', () => {
    const rawlins = { label: 'Rawlins, WY, USA', lat: 41.79, lon: -107.24 }
    const outcome = applyAction(FILLED, {
      type: 'use_place',
      label: 'Use Rawlins, WY, USA (2 mi away)',
      field: 'destination',
      place: rawlins,
    })
    expect(outcome.form.destination).toEqual(rawlins)
    expect(outcome.replan).toBe(true)
  })

  it('Pick another point: focuses the field without planning', () => {
    const outcome = applyAction(FILLED, {
      type: 'edit_field',
      label: 'Pick another point',
      field: 'destination',
    })
    expect(outcome).toEqual({ form: FILLED, replan: false, focus: 'destination' })
  })

  it('Try again: same trip, plans again', () => {
    expect(applyAction(FILLED, { type: 'retry', label: 'Try again' })).toEqual({
      form: FILLED,
      replan: true,
    })
  })
})

describe('remainingErrors', () => {
  it('clears an error as soon as its field is fixed', () => {
    const errors = { origin: 'Pick a starting point from the suggestions.', load: 'Enter the cargo load.' }
    expect(remainingErrors(errors, { ...EMPTY_FORM, origin: DENVER })).toEqual({ load: 'Enter the cargo load.' })
  })

  it("doesn't show new errors while the driver is still filling in the form", () => {
    expect(remainingErrors({}, EMPTY_FORM)).toEqual({})
    expect(remainingErrors({ load: 'Enter the cargo load.' }, { ...EMPTY_FORM, load: '100' })).toEqual({})
  })
})
