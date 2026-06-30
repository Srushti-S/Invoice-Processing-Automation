import type { ReactNode } from 'react'

type Props = {
  title: string
  meta?: string
  children: ReactNode
}

export function DetailSection({ title, meta, children }: Props) {
  return (
    <section className="border-t border-line pt-4">
      <div className="mb-2 flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-ink">{title}</h3>
        {meta && <span className="text-xs text-muted">{meta}</span>}
      </div>
      {children}
    </section>
  )
}
