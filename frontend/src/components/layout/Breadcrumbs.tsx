import { ChevronRight } from "lucide-react"
import { Link } from "react-router-dom"

export interface BreadcrumbItem {
  label: string
  to?: string
}

interface Props {
  items: BreadcrumbItem[]
}

export function Breadcrumbs({ items }: Props) {
  return (
    <nav aria-label="Breadcrumb" className="text-sm text-muted-foreground">
      <ol className="flex flex-wrap items-center gap-1">
        {items.map((item, idx) => {
          const isLast = idx === items.length - 1
          return (
            <li key={`${item.label}-${idx}`} className="flex items-center gap-1">
              {idx > 0 && <ChevronRight className="size-3.5 shrink-0" aria-hidden />}
              {isLast || !item.to ? (
                <span className="text-foreground" aria-current={isLast ? "page" : undefined}>
                  {item.label}
                </span>
              ) : (
                <Link to={item.to} className="hover:underline">
                  {item.label}
                </Link>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
