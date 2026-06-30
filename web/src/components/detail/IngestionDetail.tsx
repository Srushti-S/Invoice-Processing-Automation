import type { Invoice } from '../../types'
import { money } from '../../lib/format'
import { DetailSection } from './DetailSection'
import { Field } from './Field'

export function IngestionDetail({ invoice }: { invoice: Invoice }) {
  return (
    <DetailSection title="Ingestion">
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        <Field label="Amount" value={money(invoice.amount, invoice.currency)} />
        <Field label="Currency" value={invoice.currency} />
        <Field label="Due" value={invoice.due_date ?? invoice.raw_due_date_text ?? '—'} />
      </div>
      {invoice.items.length > 0 && (
        <table className="mt-3 w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
              <th className="py-1 pr-3 font-medium">Item</th>
              <th className="py-1 pr-3 text-right font-medium">Qty</th>
              <th className="py-1 pr-3 text-right font-medium">Unit</th>
            </tr>
          </thead>
          <tbody>
            {invoice.items.map((li, i) => (
              <tr key={i} className="border-b border-line/60 last:border-0">
                <td className="py-1 pr-3 font-mono text-ink">{li.item}</td>
                <td className="py-1 pr-3 text-right text-ink">{li.quantity}</td>
                <td className="py-1 pr-3 text-right text-muted">{money(li.unit_price, invoice.currency)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {invoice.extraction_warnings.length > 0 && (
        <p className="mt-2 text-xs text-review">Warnings: {invoice.extraction_warnings.join('; ')}</p>
      )}
    </DetailSection>
  )
}
