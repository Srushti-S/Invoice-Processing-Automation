import { decisionColor, decisionText } from '../lib/status'

export function DecisionLabel({ status }: { status: string }) {
  return (
    <span className={`font-medium ${decisionColor[status] ?? 'text-ink'}`}>
      {decisionText[status] ?? status}
    </span>
  )
}
