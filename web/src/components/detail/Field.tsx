export function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-muted">{label}: </span>
      <span className="text-ink">{value}</span>
    </div>
  )
}
