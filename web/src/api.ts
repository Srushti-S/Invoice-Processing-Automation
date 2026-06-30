import type { InventoryItem, Provider, Result, Summary } from './types'

async function post<T>(url: string, body: unknown): Promise<T> {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error(`${url} -> ${r.status}`)
  return r.json()
}

async function get<T>(url: string): Promise<T> {
  const r = await fetch(url)
  if (!r.ok) throw new Error(`${url} -> ${r.status}`)
  return r.json()
}

export const api = {
  providers: () => get<Provider[]>('/api/providers'),
  inventory: () => get<InventoryItem[]>('/api/inventory'),
  batch: (folder: string, provider: string) =>
    post<{ results: Result[]; summary: Summary }>('/api/batch', { folder, provider }),
  override: (path: string, decision: string, provider: string, note?: string) =>
    post<Result>('/api/override', { path, decision, provider, note }),
  reset: () => post<{ status: string }>('/api/reset', {}),
}
