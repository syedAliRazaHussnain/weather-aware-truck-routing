// Times are shown in the origin's zone, with its abbreviation (#7).
import { describe, expect, it } from 'vitest'
import {
  formatClock,
  formatDayClock,
  formatDuration,
  nowForForm,
  sliderLabel,
  zoneAbbreviation,
} from './time'

const DENVER = 'America/Denver'

describe('time', () => {
  it('shows an ETA as a clock time in the origin zone', () => {
    expect(formatClock('2026-11-08T08:31-07:00', DENVER)).toBe('8:31 AM')
  })

  it('shows the same moment in a different zone when asked', () => {
    expect(formatClock('2026-11-08T08:31-07:00', 'Asia/Karachi')).toBe('8:31 PM')
  })

  it('adds the weekday for times on the slider', () => {
    expect(formatDayClock('2026-11-09T01:00-07:00', DENVER)).toBe('Mon 1:00 AM')
  })

  it('names the zone, including the daylight-saving change', () => {
    expect(zoneAbbreviation('2026-11-08T08:00-07:00', DENVER)).toBe('MST')
    expect(zoneAbbreviation('2026-07-08T08:00-06:00', DENVER)).toBe('MDT')
  })

  it.each([
    [53 * 60, '53 min'],
    [65 * 60, '1 h 05 min'],
    [10 * 3600 + 12 * 60, '10 h 12 min'],
  ])('formats %i seconds as %s', (seconds, text) => {
    expect(formatDuration(seconds)).toBe(text)
  })

  it('labels a slider hour from the heatmap start (#47)', () => {
    expect(sliderLabel('2026-11-08T08:00-07:00', 17, DENVER)).toBe('+17 h · Mon 1:00 AM')
  })

  it('gives "now" in the form format, in the origin zone', () => {
    const now = new Date('2026-11-07T12:30:00Z')
    expect(nowForForm(DENVER, now)).toBe('2026-11-07T05:30')
    expect(nowForForm('Asia/Karachi', now)).toBe('2026-11-07T17:30')
  })
})
