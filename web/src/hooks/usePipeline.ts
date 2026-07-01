import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import { RISK_REJECT } from '../lib/status'
import type { InventoryItem, Provider, Result, Summary } from '../types'

export function usePipeline() {
  const [providers, setProviders] = useState<Provider[]>([])
  const [provider, setProvider] = useState('mock')
  const [folder, setFolder] = useState('sample')
  const [results, setResults] = useState<Result[]>([])
  const [summary, setSummary] = useState<Summary | null>(null)
  const [inventory, setInventory] = useState<InventoryItem[]>([])
  const [selected, setSelected] = useState<Result | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function runBatch(nextFolder = folder, nextProvider = provider) {
    setLoading(true)
    setError(null)
    try {
      const [out, inv] = await Promise.all([api.batch(nextFolder, nextProvider), api.inventory()])
      setResults(out.results)
      setSummary(out.summary)
      setInventory(inv)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  async function reset() {
    setError(null)
    try {
      await api.reset()
      await runBatch()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function override(decision: string) {
    if (!selected?.invoice.source_path) return
    try {
      const updated = await api.override(selected.invoice.source_path, decision, provider, 'dashboard override')
      setResults((rows) => rows.map((r) => (r.invoice.source_path === updated.invoice.source_path ? updated : r)))
      setSelected(updated)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  function changeFolder(next: string) {
    setFolder(next)
    runBatch(next)
  }

  function changeProvider(next: string) {
    setProvider(next)
    runBatch(folder, next)
  }

  const didInit = useRef(false)
  useEffect(() => {
    if (didInit.current) return
    didInit.current = true
    api.providers().then(setProviders).catch(() => {})
    api.reset().catch(() => {}).finally(() => runBatch('sample', 'mock'))
  }, [])

  const fraudBlocked = useMemo(
    () => results.find((r) => r.status === 'REJECTED' && (r.approval?.risk_score ?? 0) >= RISK_REJECT) ?? null,
    [results],
  )

  return {
    providers,
    provider,
    folder,
    results,
    summary,
    inventory,
    selected,
    loading,
    error,
    fraudBlocked,
    setSelected,
    runBatch,
    reset,
    override,
    changeFolder,
    changeProvider,
  }
}
