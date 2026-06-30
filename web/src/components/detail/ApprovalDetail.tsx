import type { Approval } from '../../types'
import { RISK_REJECT, RISK_REVIEW } from '../../lib/status'
import { DetailSection } from './DetailSection'

function riskColor(score: number): string {
  if (score >= RISK_REJECT) return 'bg-reject'
  if (score >= RISK_REVIEW) return 'bg-review'
  return 'bg-ok'
}

export function ApprovalDetail({ approval }: { approval: Approval }) {
  return (
    <DetailSection title="Approval" meta={`risk ${approval.risk_score}/100`}>
      <div className="mb-3 h-1 w-full rounded-sm bg-line">
        <div
          className={`h-1 rounded-sm ${riskColor(approval.risk_score)}`}
          style={{ width: `${approval.risk_score}%` }}
        />
      </div>
      {approval.high_scrutiny && (
        <p className="mb-1 text-xs text-review">Over $10K — additional scrutiny required.</p>
      )}
      {approval.tool_calls.length > 0 && (
        <div className="mb-2">
          <div className="mb-1 text-xs text-muted">Tool calls:</div>
          <ul className="ml-4 list-disc text-xs font-mono text-ink">
            {approval.tool_calls.map((t, i) => <li key={i}>{t}</li>)}
          </ul>
        </div>
      )}
      {approval.fraud_signals.length > 0 && (
        <ul className="mb-2 ml-4 list-disc text-sm text-ink">
          {approval.fraud_signals.map((s, i) => <li key={i}>{s}</li>)}
        </ul>
      )}
      <p className="text-sm text-ink">
        <span className="text-muted">Rationale: </span>{approval.rationale}
      </p>
      {approval.reflection && (
        <p className={`mt-2 text-sm ${approval.revised ? 'text-review' : 'text-muted'}`}>
          <span className="font-medium">Reflection:</span> {approval.reflection}
          {approval.revised && <span className="ml-1 font-medium">(decision revised)</span>}
        </p>
      )}
    </DetailSection>
  )
}
