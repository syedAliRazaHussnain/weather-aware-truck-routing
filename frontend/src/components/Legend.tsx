// Level names next to their colours, so colour is never the only signal (#54).
import { LEVELS, LEVEL_COLORS, LEVEL_LABELS, UNKNOWN_COLOR } from '../lib/risk'

export function Legend({ showUnknown }: { showUnknown: boolean }) {
  return (
    <ul className="legend" aria-label="Risk levels">
      {LEVELS.map((level) => (
        <li key={level}>
          <span className="swatch" style={{ background: LEVEL_COLORS[level] }} />
          {LEVEL_LABELS[level]}
        </li>
      ))}
      {showUnknown && (
        <li>
          <span className="swatch" style={{ background: UNKNOWN_COLOR }} />
          Unknown
        </li>
      )}
    </ul>
  )
}
