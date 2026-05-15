import type { ReactNode } from "react"

import { Breadcrumbs, type BreadcrumbItem } from "@/components/layout/Breadcrumbs"

interface Props {
  title: string
  subtitle?: ReactNode
  breadcrumbs?: BreadcrumbItem[]
  actions?: ReactNode
}

export function PageHeader({ title, subtitle, breadcrumbs, actions }: Props) {
  return (
    <header className="space-y-2">
      {breadcrumbs && <Breadcrumbs items={breadcrumbs} />}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">{title}</h1>
          {subtitle && (
            <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
          )}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
    </header>
  )
}
