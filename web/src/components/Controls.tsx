import type { Provider } from '../types'

type Props = {
  folder: string
  provider: string
  providers: Provider[]
  loading: boolean
  onFolder: (value: string) => void
  onProvider: (value: string) => void
  onRun: () => void
  onReset: () => void
}

const selectClass = 'rounded-sm border border-line bg-white px-2.5 py-1.5 text-sm text-ink'

export function Controls({ folder, provider, providers, loading, onFolder, onProvider, onRun, onReset }: Props) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <select value={folder} onChange={(e) => onFolder(e.target.value)} className={selectClass}>
        <option value="sample">Sample invoices (20)</option>
        <option value="custom">Custom edge cases (2)</option>
      </select>
      <select value={provider} onChange={(e) => onProvider(e.target.value)} className={selectClass}>
        {providers.filter((p) => p.ready).map((p) => (
          <option key={p.id} value={p.id}>{p.label}</option>
        ))}
      </select>
      <button
        onClick={onRun}
        disabled={loading}
        className="rounded-sm bg-accent px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50">
        {loading ? 'Running…' : 'Re-run batch'}
      </button>
      <button
        onClick={onReset}
        className="rounded-sm border border-line bg-white px-3 py-1.5 text-sm text-ink hover:border-muted">
        Reset
      </button>
    </div>
  )
}
