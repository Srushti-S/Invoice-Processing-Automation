import type { Result } from '../types'
import { money } from '../lib/format'
import { DecisionLabel } from './DecisionLabel'

type Props = {
  results: Result[]
  onSelect: (result: Result) => void
}

export function ResultsTable({ results, onSelect }: Props) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[680px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
            <th className="py-2 pr-4 font-medium">Invoice</th>
            <th className="py-2 pr-4 font-medium">Vendor</th>
            <th className="py-2 pr-4 text-right font-medium">Amount</th>
            <th className="py-2 pr-4 font-medium">Issues</th>
            <th className="py-2 pr-4 font-medium">Decision</th>
            <th className="py-2 pr-4 text-right font-medium">At risk</th>
            <th className="py-2 font-medium"></th>
          </tr>
        </thead>
        <tbody>
          {results.map((r, i) => {
            const codes = Array.from(new Set((r.validation?.issues ?? []).map((x) => x.code)))
            return (
              <tr
                key={r.invoice.source_path ?? `${r.invoice.invoice_number}-${i}`}
                onClick={() => onSelect(r)}
                className="cursor-pointer border-b border-line/70 hover:bg-black/[0.02]">
                <td className="py-2.5 pr-4">
                  <span className="font-mono text-ink">{r.invoice.invoice_number ?? '—'}</span>
                </td>
                <td className="max-w-[220px] truncate py-2.5 pr-4 text-ink">{r.invoice.vendor ?? '—'}</td>
                <td className="py-2.5 pr-4 text-right text-ink">{money(r.invoice.amount, r.invoice.currency)}</td>
                <td className="py-2.5 pr-4 text-muted">{codes.length ? codes.join(', ') : '—'}</td>
                <td className="py-2.5 pr-4"><DecisionLabel status={r.status} /></td>
                <td className="py-2.5 pr-4 text-right text-muted">
                  {r.amount_at_risk && Number(r.amount_at_risk) > 0
                    ? money(r.amount_at_risk, r.invoice.currency)
                    : '—'}
                </td>
                <td className="py-2.5 text-right">
                  <button
                    onClick={(e) => { e.stopPropagation(); onSelect(r) }}
                    className="text-accent hover:underline">
                    View
                  </button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
