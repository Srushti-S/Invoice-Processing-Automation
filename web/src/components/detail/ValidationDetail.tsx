import type { Validation } from '../../types'
import { money } from '../../lib/format'
import { DetailSection } from './DetailSection'
import { SeverityTag } from '../SeverityTag'

export function ValidationDetail({ validation }: { validation: Validation }) {
  const aggregated = Object.entries(validation.aggregated_items)
    .map(([item, qty]) => `${item}: ${qty}`)
    .join('   ')
  const delta = validation.total_delta
  return (
    <DetailSection title="Validation" meta={validation.status}>
      {aggregated && <p className="mb-2 text-xs text-muted">Aggregated stock check: {aggregated}</p>}
      {delta && Number(delta) !== 0 && (
        <p className="mb-2 text-xs text-review">
          Arithmetic: stated {money(validation.stated_total)} vs recomputed {money(validation.recomputed_total)} (delta{' '}
          {Number(delta) > 0 ? '+' : ''}{delta})
        </p>
      )}
      {validation.issues.length === 0 ? (
        <p className="text-sm text-ok">No issues.</p>
      ) : (
        <ul className="space-y-1">
          {validation.issues.map((issue, i) => (
            <li key={i} className="text-sm">
              <SeverityTag severity={issue.severity} />{' '}
              <span className="font-mono text-ink">{issue.code}</span>
              <span className="text-muted"> — {issue.detail}</span>
            </li>
          ))}
        </ul>
      )}
    </DetailSection>
  )
}
