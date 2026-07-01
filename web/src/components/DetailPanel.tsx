import type { Result } from '../types'
import { DecisionLabel } from './DecisionLabel'
import { IngestionDetail } from './detail/IngestionDetail'
import { ValidationDetail } from './detail/ValidationDetail'
import { ApprovalDetail } from './detail/ApprovalDetail'
import { OutcomeDetail } from './detail/OutcomeDetail'

type Props = {
  result: Result
  onClose: () => void
  onOverride: (decision: string) => void
}

export function DetailPanel({ result, onClose, onOverride }: Props) {
  const inv = result.invoice
  return (
    <div className="fixed inset-0 z-30 flex justify-end bg-ink/20" onClick={onClose}>
      <div
        className="h-full w-full max-w-xl overflow-y-auto border-l border-line bg-paper p-4 sm:p-6"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between border-b border-line pb-4">
          <div>
            <div className="font-mono text-lg text-ink">{inv.invoice_number ?? '—'}</div>
            <div className="text-sm text-muted">{inv.vendor ?? '—'}</div>
          </div>
          <div className="flex items-center gap-4">
            <DecisionLabel status={result.status} />
            <button onClick={onClose} className="rounded-sm border border-line px-2.5 py-1 text-sm text-ink hover:border-muted">Close</button>
          </div>
        </div>
        <div className="space-y-4">
          <IngestionDetail invoice={inv} />
          {result.validation && <ValidationDetail validation={result.validation} />}
          {result.approval && <ApprovalDetail approval={result.approval} />}
          <OutcomeDetail result={result} onOverride={onOverride} />
        </div>
      </div>
    </div>
  )
}
