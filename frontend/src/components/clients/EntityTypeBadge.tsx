import { Badge } from "@/components/ui/badge"
import { ENTITY_TYPE_LABELS, type EntityType } from "@/types/client"

const STYLE: Record<EntityType, string> = {
  company: "bg-blue-100 text-blue-800 hover:bg-blue-100",
  individual: "bg-green-100 text-green-800 hover:bg-green-100",
  partnership: "bg-purple-100 text-purple-800 hover:bg-purple-100",
  ngo: "bg-amber-100 text-amber-800 hover:bg-amber-100",
  bank: "bg-slate-200 text-slate-800 hover:bg-slate-200",
}

export function EntityTypeBadge({ type }: { type: EntityType }) {
  return (
    <Badge variant="secondary" className={STYLE[type]}>
      {ENTITY_TYPE_LABELS[type]}
    </Badge>
  )
}
