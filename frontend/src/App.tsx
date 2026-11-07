// The app: form and results on the left, the map on the right (stacked on phones, #55).
// All state lives here and flows down (docs/ARCHITECTURE.md, diagram 5).
import { useCallback, useEffect, useRef, useState } from 'react'
import { wakeServer } from './api/client'
import type { Action, PlanRequest, RouteResult } from './api/types'
import { HourSlider } from './components/HourSlider'
import { Legend } from './components/Legend'
import { MapView } from './components/MapView'
import { ProblemPanel } from './components/ProblemPanel'
import { ResultsPanel } from './components/ResultsPanel'
import { TripForm } from './components/TripForm'
import { usePlan } from './hooks/usePlan'
import {
  EMPTY_FORM,
  type FormErrors,
  type FormField,
  type TripForm as Form,
  applyAction,
  remainingErrors,
  toPlanRequest,
} from './lib/form'

export default function App() {
  const [form, setForm] = useState<Form>(EMPTY_FORM)
  const [errors, setErrors] = useState<FormErrors>({})
  const [selectedId, setSelectedId] = useState<RouteResult['id'] | null>(null)
  const [hour, setHour] = useState(0)
  const [openCheckpoint, setOpenCheckpoint] = useState<number | null>(null)
  const [center, setCenter] = useState<{ lat: number; lon: number }>()
  const { plan, problem, loading, slow, run } = usePlan()

  const fieldRefs: Record<FormField, React.RefObject<HTMLInputElement | null>> = {
    origin: useRef<HTMLInputElement>(null),
    destination: useRef<HTMLInputElement>(null),
    departure: useRef<HTMLInputElement>(null),
    load: useRef<HTMLInputElement>(null),
  }

  useEffect(wakeServer, []) // #58: wake the free server while the driver types

  // A new plan: select the recommended route (#57) and go back to departure hour.
  useEffect(() => {
    setSelectedId(plan?.recommended ?? plan?.routes[0]?.id ?? null)
    setHour(0)
    setOpenCheckpoint(null)
  }, [plan])

  const submit = useCallback(
    (next: Form) => {
      const checked = toPlanRequest(next)
      if ('errors' in checked) {
        setErrors(checked.errors)
        return
      }
      setErrors({})
      void run(checked.request as PlanRequest)
    },
    [run],
  )

  const onAction = useCallback(
    (action: Action) => {
      const outcome = applyAction(form, action)
      setForm(outcome.form)
      if (outcome.focus) fieldRefs[outcome.focus].current?.focus()
      if (outcome.replan) submit(outcome.form)
    },
    // fieldRefs are stable refs
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [form, submit],
  )

  return (
    <div className="layout">
      <aside className="panel">
        <header className="brand">
          <h1>Weather-Aware Truck Routing</h1>
          <p>Up to three truck routes, checked for wind, rain and snow at every checkpoint.</p>
        </header>
        <TripForm
          form={form}
          errors={errors}
          loading={loading}
          focus={center}
          fieldRefs={fieldRefs}
          onChange={(next) => {
            setForm(next)
            setErrors((previous) => remainingErrors(previous, next))
          }}
          onSubmit={() => submit(form)}
        />
        {loading && (
          <p className="status" role="status">
            {slow ? 'Waking up the server, this takes up to a minute the first time…' : 'Planning your trip…'}
          </p>
        )}
        {problem && <ProblemPanel problem={problem} onAction={onAction} />}
        {plan && (
          <ResultsPanel
            plan={plan}
            selectedId={selectedId}
            onSelect={(id) => {
              setSelectedId(id)
              setOpenCheckpoint(null)
            }}
            onAction={onAction}
          />
        )}
      </aside>
      <main className="map-area">
        <MapView
          plan={plan}
          origin={form.origin}
          destination={form.destination}
          selectedId={selectedId}
          hour={hour}
          openCheckpoint={openCheckpoint}
          onSelectRoute={(id) => {
            setSelectedId(id)
            setOpenCheckpoint(null)
          }}
          onOpenCheckpoint={setOpenCheckpoint}
          onCenter={setCenter}
        />
        {plan && (
          <div className="map-overlay">
            {plan.heatmap && (
              <HourSlider heatmap={plan.heatmap} timezone={plan.timezone} hour={hour} onHour={setHour} />
            )}
            <Legend showUnknown={plan.weather_status !== 'ok'} />
          </div>
        )}
      </main>
    </div>
  )
}
