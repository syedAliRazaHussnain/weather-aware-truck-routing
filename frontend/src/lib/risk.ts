// One palette for checkpoints, route segments, heatmap squares and the legend (#54).
// Labels are always shown next to colours, so colour is never the only signal.

import type { Level } from '../api/types'

export const LEVELS: readonly Level[] = [0, 1, 2, 3, 4]

export const LEVEL_LABELS: Record<Level, string> = {
  0: 'Low',
  1: 'Moderate',
  2: 'High',
  3: 'Severe',
  4: 'No Travel',
}

export const LEVEL_COLORS: Record<Level, string> = {
  0: '#3fa34d', // green
  1: '#e8b416', // yellow
  2: '#f07c1b', // orange
  3: '#d93025', // red
  4: '#6b1d86', // purple: clearly different from red
}

/** Grey for "weather unknown": never shown as a risk colour (#39). */
export const UNKNOWN_COLOR = '#9aa0a6'

/** The colour for a level, or grey when the weather is unknown. */
export function levelColor(level: Level | null): string {
  return level === null ? UNKNOWN_COLOR : LEVEL_COLORS[level]
}

/** The name for a level, or "Weather unknown". */
export function levelLabel(level: Level | null): string {
  return level === null ? 'Weather unknown' : LEVEL_LABELS[level]
}

/** A MapLibre colour expression that colours a feature by a numeric level property. */
export function levelColorExpression(property: string): unknown[] {
  return [
    'match',
    ['get', property],
    ...LEVELS.flatMap((level) => [level, LEVEL_COLORS[level]]),
    UNKNOWN_COLOR,
  ]
}
