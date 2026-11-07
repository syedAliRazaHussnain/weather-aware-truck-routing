// The trip form's state, checking it, and what each problem button does to it.
// Pure functions, so the rules are tested without rendering anything.

import type { Action, Place, PlanRequest } from '../api/types'
import { type LoadUnit, toPounds } from './units'

export type Interval = 10 | 25 | 50
export type FormField = 'origin' | 'destination' | 'departure' | 'load'

export interface TripForm {
  origin: Place | null
  destination: Place | null
  leaveNow: boolean // #10: the default; the server uses "now" at the origin
  departure: string // "2026-11-08T08:00", origin's local time (#7), used when !leaveNow
  load: string // as typed, so the box can be empty while editing
  loadUnit: LoadUnit
  interval: Interval // #1
}

export const EMPTY_FORM: TripForm = {
  origin: null,
  destination: null,
  leaveNow: true,
  departure: '',
  load: '',
  loadUnit: 'lb',
  interval: 25,
}

export const MAX_LOAD_LB = 150_000 // #2: same limit as the server

export type FormErrors = Partial<Record<FormField, string>>

/** The form as an API request, or the fields that need fixing first. */
export function toPlanRequest(form: TripForm): { request: PlanRequest } | { errors: FormErrors } {
  const errors: FormErrors = {}
  if (!form.origin) errors.origin = 'Pick a starting point from the suggestions.' // #5
  if (!form.destination) errors.destination = 'Pick a destination from the suggestions.'
  if (!form.leaveNow && !form.departure) errors.departure = 'Choose a departure time.'
  const load = Number(form.load)
  const loadLb = toPounds(load, form.loadUnit)
  if (form.load.trim() === '' || !Number.isFinite(load) || load < 0) {
    errors.load = 'Enter the cargo load.'
  } else if (loadLb > MAX_LOAD_LB) {
    errors.load = `That's over ${MAX_LOAD_LB.toLocaleString('en-US')} lb. Check for an extra zero.`
  }
  if (Object.keys(errors).length > 0 || !form.origin || !form.destination) return { errors }
  return {
    request: {
      origin: form.origin,
      destination: form.destination,
      ...(form.leaveNow ? {} : { departure: form.departure }),
      load_lb: loadLb,
      interval_mi: form.interval,
    },
  }
}

/** After an edit, keep only the errors that still apply; never add new ones mid-typing. */
export function remainingErrors(previous: FormErrors, form: TripForm): FormErrors {
  if (Object.keys(previous).length === 0) return previous
  const checked = toPlanRequest(form)
  const now: FormErrors = 'errors' in checked ? checked.errors : {}
  const kept: FormErrors = {}
  for (const field of Object.keys(previous) as FormField[]) {
    if (now[field]) kept[field] = now[field]
  }
  return kept
}

/** What pressing a problem's button does: a new form, whether to plan again, what to focus. */
export interface ActionOutcome {
  form: TripForm
  replan: boolean
  focus?: FormField
}

export function applyAction(form: TripForm, action: Action): ActionOutcome {
  switch (action.type) {
    case 'retry':
      return { form, replan: true }
    case 'set_departure':
      return { form: { ...form, leaveNow: false, departure: action.value }, replan: true }
    case 'set_interval':
      return { form: { ...form, interval: action.value }, replan: true }
    case 'use_place':
      return { form: { ...form, [action.field]: action.place }, replan: true }
    case 'edit_field':
      return { form, replan: false, focus: action.field }
  }
}
