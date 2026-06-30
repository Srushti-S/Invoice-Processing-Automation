import type { Result } from '../../types'
import { money } from '../../lib/format'
import { DetailSection } from './DetailSection'

type Props = {
  result: Result
  onOverride: (decision: string) => void
}

export function OutcomeDetail({ result, onOverride }: Props) {
  const inv = result.invoice
  return (
    <DetailSection title="Payment / outcome">
      {result.status === 'OK' && (
        <p className="text-sm text-ok">
          Paid {money(inv.amount, inv.currency)} to {inv.vendor} (payment {String(result.payment?.payment_id)}).
        </p>
      )}
      {result.status === 'REJECTED' && (
        <p className="text-sm text-reject">
          Rejected. {money(result.amount_at_risk, inv.currency)} not paid.
        </p>
      )}
      {result.status === 'NEEDS_HUMAN_REVIEW' && (
        <p className="text-sm text-review">
          Held for review. {money(inv.amount, inv.currency)} not paid.
        </p>
      )}
      {result.status === 'SUPERSEDED' && (
        <p className="text-sm text-muted">Superseded. {result.dedup_reason}.</p>
      )}
      {result.status !== 'OK' && inv.source_path && (
        <div className="mt-3 flex items-center gap-2">
          <span className="text-xs text-muted">Human override:</span>
          <button
            onClick={() => onOverride('APPROVE')}
            className="rounded-sm bg-accent px-3 py-1 text-xs font-medium text-white">
            Approve and pay
          </button>
          <button
            onClick={() => onOverride('REJECT')}
            className="rounded-sm border border-line px-3 py-1 text-xs text-ink hover:border-muted">
            Reject
          </button>
        </div>
      )}
    </DetailSection>
  )
}
