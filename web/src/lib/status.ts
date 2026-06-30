export const decisionText: Record<string, string> = {
  OK: 'Paid',
  REJECTED: 'Rejected',
  NEEDS_HUMAN_REVIEW: 'Needs review',
  SUPERSEDED: 'Superseded',
  ERROR: 'Error',
}

export const decisionColor: Record<string, string> = {
  OK: 'text-ok',
  REJECTED: 'text-reject',
  NEEDS_HUMAN_REVIEW: 'text-review',
  SUPERSEDED: 'text-muted',
  ERROR: 'text-reject',
}

export const severityColor: Record<string, string> = {
  FAIL: 'text-reject',
  WARN: 'text-review',
  INFO: 'text-muted',
}

export const RISK_REJECT = 60
export const RISK_REVIEW = 30
