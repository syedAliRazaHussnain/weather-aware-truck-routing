// The trip form: where from, where to, when, how heavy, and how often to check (#1-#5).
import type { RefObject } from 'react'
import type { FormErrors, FormField, Interval, TripForm as Form } from '../lib/form'
import { convertLoad, type LoadUnit } from '../lib/units'
import { PlaceInput } from './PlaceInput'

interface Props {
  form: Form
  errors: FormErrors
  loading: boolean
  focus?: { lat: number; lon: number }
  fieldRefs: Record<FormField, RefObject<HTMLInputElement | null>>
  onChange: (form: Form) => void
  onSubmit: () => void
}

const INTERVALS: Interval[] = [10, 25, 50]

export function TripForm({ form, errors, loading, focus, fieldRefs, onChange, onSubmit }: Props) {
  const { origin: originRef, destination: destinationRef, departure: departureRef, load: loadRef } = fieldRefs
  const set = (patch: Partial<Form>) => onChange({ ...form, ...patch })

  function switchUnit(unit: LoadUnit) {
    const value = Number(form.load)
    const load = form.load.trim() === '' || !Number.isFinite(value) ? form.load : String(convertLoad(value, form.loadUnit, unit))
    set({ loadUnit: unit, load })
  }

  return (
    <form
      className="trip-form"
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit()
      }}
      noValidate
    >
      <PlaceInput
        label="From"
        placeholder="City, address or place"
        value={form.origin}
        onChange={(origin) => set({ origin })}
        focus={focus}
        error={errors.origin}
        inputRef={originRef}
      />
      <PlaceInput
        label="To"
        placeholder="City, address or place"
        value={form.destination}
        onChange={(destination) => set({ destination })}
        focus={focus}
        error={errors.destination}
        inputRef={destinationRef}
      />

      <fieldset className="field">
        <legend>Departure</legend>
        <div className="segmented">
          <button type="button" aria-pressed={form.leaveNow} onClick={() => set({ leaveNow: true })}>
            Leave now
          </button>
          <button type="button" aria-pressed={!form.leaveNow} onClick={() => set({ leaveNow: false })}>
            Leave later
          </button>
        </div>
        {!form.leaveNow && (
          <>
            <input
              ref={departureRef}
              type="datetime-local"
              aria-label="Departure time"
              aria-invalid={Boolean(errors.departure)}
              value={form.departure}
              onChange={(event) => set({ departure: event.target.value })}
            />
            <p className="hint">Local time at the starting point.</p>
          </>
        )}
        {errors.departure && <p className="error">{errors.departure}</p>}
      </fieldset>

      <div className="field">
        <label htmlFor="load">Cargo load</label>
        <div className="load-row">
          <input
            id="load"
            ref={loadRef}
            type="number"
            inputMode="numeric"
            min={0}
            step={100}
            placeholder="42000"
            aria-invalid={Boolean(errors.load)}
            value={form.load}
            onChange={(event) => set({ load: event.target.value })}
          />
          <div className="segmented small" role="group" aria-label="Load unit">
            {(['lb', 'kg'] as const).map((unit) => (
              <button key={unit} type="button" aria-pressed={form.loadUnit === unit} onClick={() => switchUnit(unit)}>
                {unit}
              </button>
            ))}
          </div>
        </div>
        {errors.load && <p className="error">{errors.load}</p>}
      </div>

      <fieldset className="field">
        <legend>Check weather every</legend>
        <div className="segmented">
          {INTERVALS.map((miles) => (
            <button key={miles} type="button" aria-pressed={form.interval === miles} onClick={() => set({ interval: miles })}>
              {miles} mi
            </button>
          ))}
        </div>
      </fieldset>

      <button type="submit" className="primary" disabled={loading}>
        {loading ? 'Planning…' : 'Plan trip'}
      </button>
    </form>
  )
}
