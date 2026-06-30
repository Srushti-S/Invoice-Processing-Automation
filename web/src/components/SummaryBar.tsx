import type { Summary } from '../types'
import { money } from '../lib/format'

export function SummaryBar({ summary }: { summary: Summary }) {
  const stats = [
    { label: 'Processed', value: summary.total },
    { label: 'Paid', value: summary.paid },
    { label: 'Paid value', value: money(summary.paid_total) },
    { label: 'Rejected', value: summary.rejected },
    { label: 'Held / superseded', value: `${summary.review} / ${summary.superseded}` },
    { label: 'Flagged, not paid', value: money(summary.amount_at_risk_flagged) },
  ]
  return (
    <div className="mt-6 grid grid-cols-2 gap-4 border-b border-line pb-6 sm:grid-cols-3 lg:grid-cols-6">
      {stats.map((s) => (
        <div key={s.label}>
          <div className="text-xs uppercase tracking-wide text-muted">{s.label}</div>
          <div className="mt-1 text-lg font-semibold text-ink">{s.value}</div>
        </div>
      ))}
    </div>
  )
}
