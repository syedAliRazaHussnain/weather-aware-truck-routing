// Load in lb or kg; the API always gets lb (#2).
import { describe, expect, it } from 'vitest'
import { convertLoad, toPounds } from './units'

describe('units', () => {
  it('sends lb as typed', () => {
    expect(toPounds(42000, 'lb')).toBe(42000)
  })

  it('converts kg to whole pounds', () => {
    expect(toPounds(20000, 'kg')).toBe(44092)
  })

  it('converts the box when the switch flips, both ways', () => {
    expect(convertLoad(20000, 'kg', 'lb')).toBe(44092)
    expect(convertLoad(44092, 'lb', 'kg')).toBe(20000)
    expect(convertLoad(500, 'lb', 'lb')).toBe(500)
  })
})
