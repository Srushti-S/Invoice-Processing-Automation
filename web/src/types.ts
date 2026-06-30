export interface LineItem {
  item: string
  quantity: number
  unit_price: string | null
  line_total: string | null
  note: string | null
}

export interface Invoice {
  invoice_number: string | null
  vendor: string | null
  amount: string | null
  currency: string
  due_date: string | null
  raw_due_date_text: string | null
  items: LineItem[]
  subtotal: string | null
  tax_amount: string | null
  other_charges: string | null
  revision: string | null
  notes: string | null
  source_format: string | null
  source_path: string | null
  extraction_method: string | null
  extraction_warnings: string[]
}

export interface Issue {
  code: string
  detail: string
  severity: 'INFO' | 'WARN' | 'FAIL'
  item: string | null
}

export interface Validation {
  status: string
  issues: Issue[]
  aggregated_items: Record<string, number>
  recomputed_total: string | null
  stated_total: string | null
  total_delta: string | null
}

export interface Approval {
  decision: string
  rationale: string
  risk_score: number
  fraud_signals: string[]
  high_scrutiny: boolean
  reflection: string | null
  revised: boolean
  tool_calls: string[]
}

export interface Result {
  invoice: Invoice
  validation: Validation | null
  approval: Approval | null
  payment: Record<string, unknown> | null
  status: string
  amount_at_risk: string | null
  dedup_reason: string | null
  logs: { node: string; msg: string }[]
  error: string | null
}

export interface Summary {
  total: string
  paid: string
  rejected: string
  review: string
  superseded: string
  errors: string
  paid_total: string
  amount_at_risk_flagged: string
}

export interface InventoryItem {
  item: string
  stock: number
}

export interface Provider {
  id: string
  label: string
  ready: boolean
  needs_key?: string | null
}
