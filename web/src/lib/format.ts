export function money(value: string | null, currency = 'USD'): string {
  if (value == null) return '—'
  const amount = Number(value).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return currency === 'USD' ? `$${amount}` : `${currency} ${amount}`
}
