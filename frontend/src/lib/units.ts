// Load can be typed in lb or kg; the API and the spec's rules use lb (#2).

export type LoadUnit = 'lb' | 'kg'

export const LB_PER_KG = 2.20462

/** A load in the chosen unit, converted to whole pounds for the API. */
export function toPounds(value: number, unit: LoadUnit): number {
  return Math.round(unit === 'kg' ? value * LB_PER_KG : value)
}

/** Convert the number in the box when the driver flips the lb/kg switch. */
export function convertLoad(value: number, from: LoadUnit, to: LoadUnit): number {
  if (from === to) return value
  return Math.round(from === 'kg' ? value * LB_PER_KG : value / LB_PER_KG)
}
