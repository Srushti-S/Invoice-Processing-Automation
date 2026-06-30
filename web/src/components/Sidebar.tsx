import type { InventoryItem, Result } from '../types'
import { money } from '../lib/format'
import { InventoryList } from './InventoryList'

type Props = {
  inventory: InventoryItem[]
  fraudBlocked: Result | null
}

export function Sidebar({ inventory, fraudBlocked }: Props) {
  return (
    <aside className="space-y-6 text-sm lg:border-l lg:border-line lg:pl-6">
      <InventoryList inventory={inventory} />
      {fraudBlocked && (
        <div className="border-l-2 border-reject pl-3 text-reject">
          Fraud blocked: <span className="font-medium">{fraudBlocked.invoice.vendor}</span> for{' '}
          {money(fraudBlocked.invoice.amount)} — risk {fraudBlocked.approval?.risk_score}/100.
        </div>
      )}
    </aside>
  )
}
