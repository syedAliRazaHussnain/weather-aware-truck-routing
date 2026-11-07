// A place box with suggestions. A trip only uses places picked from the list (#5).
import { type Ref, useId, useState } from 'react'
import type { Place } from '../api/types'
import { usePlaceSearch } from '../hooks/usePlaceSearch'

interface Props {
  label: string
  placeholder: string
  value: Place | null
  onChange: (place: Place | null) => void
  focus?: { lat: number; lon: number } // rank suggestions near the map view (#4)
  error?: string
  inputRef?: Ref<HTMLInputElement>
}

export function PlaceInput({ label, placeholder, value, onChange, focus, error, inputRef }: Props) {
  const id = useId()
  const [draft, setDraft] = useState('') // what's typed while no place is picked
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  // A picked place shows its name; this also covers buttons like "Use Rawlins, WY".
  const text = value ? value.label : draft
  const { results, failed } = usePlaceSearch(text, focus, open && !value)

  function choose(place: Place) {
    onChange(place)
    setOpen(false)
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (!open || results.length === 0) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActive((i) => (i + 1) % results.length)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActive((i) => (i - 1 + results.length) % results.length)
    } else if (event.key === 'Enter') {
      event.preventDefault()
      choose(results[active])
    } else if (event.key === 'Escape') {
      setOpen(false)
    }
  }

  const listId = `${id}-list`
  return (
    <div className="field place-input">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        ref={inputRef}
        type="text"
        role="combobox"
        aria-expanded={open && results.length > 0}
        aria-controls={listId}
        aria-invalid={Boolean(error)}
        autoComplete="off"
        placeholder={placeholder}
        value={text}
        onChange={(event) => {
          setDraft(event.target.value)
          setActive(0)
          setOpen(true)
          if (value) onChange(null) // typing again means a new place must be picked
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={onKeyDown}
      />
      {open && results.length > 0 && (
        <ul id={listId} role="listbox" className="suggestions">
          {results.map((place, i) => (
            <li
              key={`${place.label}-${place.lat}-${place.lon}`}
              role="option"
              aria-selected={i === active}
              className={i === active ? 'active' : undefined}
              onMouseDown={(event) => {
                event.preventDefault()
                choose(place)
              }}
            >
              {place.label}
            </li>
          ))}
        </ul>
      )}
      {failed && open && <p className="hint">Search is unavailable right now. Try again in a moment.</p>}
      {error && <p className="error">{error}</p>}
    </div>
  )
}
