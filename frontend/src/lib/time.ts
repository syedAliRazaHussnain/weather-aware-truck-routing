// Times on screen are always the origin's local time, labelled with its zone (#7).
// The API sends local times with offsets, plus the zone name, e.g. "America/Denver".

/** A time like "8:31 AM" in the given zone. */
export function formatClock(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat('en-US', { timeZone, hour: 'numeric', minute: '2-digit' }).format(
    new Date(iso),
  )
}

/** A day and time like "Sun 8:31 AM". */
export function formatDayClock(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat('en-US', {
    timeZone,
    weekday: 'short',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(iso))
}

/** The short zone name at a moment, e.g. "MST" or "GMT+5". */
export function zoneAbbreviation(iso: string, timeZone: string): string {
  const parts = new Intl.DateTimeFormat('en-US', { timeZone, timeZoneName: 'short' }).formatToParts(
    new Date(iso),
  )
  return parts.find((part) => part.type === 'timeZoneName')?.value ?? timeZone
}

/** A duration like "53 min" or "10 h 12 min". */
export function formatDuration(seconds: number): string {
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min`
  return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, '0')} min`
}

/** The slider's label for an hour after the heatmap start, e.g. "+17 h · Mon 1:00 AM". */
export function sliderLabel(startIso: string, hour: number, timeZone: string): string {
  const moment = new Date(new Date(startIso).getTime() + hour * 3_600_000).toISOString()
  return `+${hour} h · ${formatDayClock(moment, timeZone)}`
}

/** "Now" in the form's format ("2026-11-08T08:00"), as a local time in a zone. */
export function nowForForm(timeZone: string, now: Date = new Date()): string {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('en-CA', {
      timeZone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    })
      .formatToParts(now)
      .map((part) => [part.type, part.value]),
  )
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`
}
