import type { InventoryItem } from '../types'

export function InventoryList({ inventory }: { inventory: InventoryItem[] }) {
  return (
    <div>
      <h2 className="text-xs uppercase tracking-wide text-muted">Inventory</h2>
      <table className="mt-2 w-full text-sm">
        <tbody>
          {inventory.map((it) => (
            <tr key={it.item} className="border-b border-line/60 last:border-0">
              <td className="py-1.5 font-mono text-ink">{it.item}</td>
              <td className={`py-1.5 text-right font-medium ${it.stock === 0 ? 'text-reject' : 'text-ink'}`}>
                {it.stock}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
