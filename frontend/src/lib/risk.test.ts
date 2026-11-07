// One palette everywhere, and unknown weather is never a risk colour (#39, #54).
import { describe, expect, it } from 'vitest'
import { LEVEL_COLORS, UNKNOWN_COLOR, levelColor, levelColorExpression, levelLabel } from './risk'

describe('risk palette', () => {
  it('gives each level its own colour', () => {
    expect(new Set(Object.values(LEVEL_COLORS)).size).toBe(5)
  })

  it('shows unknown weather in grey, never as Low', () => {
    expect(levelColor(null)).toBe(UNKNOWN_COLOR)
    expect(levelColor(null)).not.toBe(LEVEL_COLORS[0])
    expect(levelLabel(null)).toBe('Weather unknown')
  })

  it('names the levels like the spec', () => {
    expect(levelLabel(4)).toBe('No Travel')
  })

  it('builds a map colour rule with every level and a grey fallback', () => {
    const rule = levelColorExpression('h17')
    expect(rule[0]).toBe('match')
    expect(rule[1]).toEqual(['get', 'h17'])
    expect(rule.at(-1)).toBe(UNKNOWN_COLOR)
    expect(rule).toHaveLength(2 + 5 * 2 + 1)
  })
})
