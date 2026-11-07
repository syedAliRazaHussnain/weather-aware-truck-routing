// The 0-48 h heatmap slider; hour 0 is the departure hour (#47, #48).
import type { Heatmap } from '../api/types'
import { sliderLabel, zoneAbbreviation } from '../lib/time'

interface Props {
  heatmap: Heatmap
  timezone: string
  hour: number
  onHour: (hour: number) => void
}

export function HourSlider({ heatmap, timezone, hour, onHour }: Props) {
  const zone = zoneAbbreviation(heatmap.start, timezone)
  return (
    <div className="hour-slider">
      <label htmlFor="hour">
        Weather at <strong>{sliderLabel(heatmap.start, hour, timezone)}</strong> {zone}
      </label>
      <input
        id="hour"
        type="range"
        min={0}
        max={heatmap.hours - 1}
        step={1}
        value={hour}
        onChange={(event) => onHour(Number(event.target.value))}
      />
    </div>
  )
}
