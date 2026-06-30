import { severityColor } from '../lib/status'

export function SeverityTag({ severity }: { severity: string }) {
  return (
    <span className={`font-mono text-xs ${severityColor[severity] ?? 'text-muted'}`}>
      {severity}
    </span>
  )
}
