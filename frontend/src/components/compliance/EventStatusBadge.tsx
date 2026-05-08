// frontend/src/components/compliance/EventStatusBadge.tsx
import { Badge } from "@/components/ui/badge"
import { EVENT_STATUS_LABELS, type EventStatus } from "@/types/compliance"

const STYLE: Record<EventStatus, string> = {
  pending: "bg-slate-100 text-slate-800 hover:bg-slate-100",
  filed: "bg-green-100 text-green-800 hover:bg-green-100",
  overdue: "bg-red-100 text-red-800 hover:bg-red-100",
  waived: "bg-slate-200 text-slate-700 hover:bg-slate-200",
  na: "bg-slate-200 text-slate-500 italic hover:bg-slate-200",
}

export function EventStatusBadge({ status }: { status: EventStatus }) {
  return (
    <Badge variant="secondary" className={STYLE[status]}>
      {EVENT_STATUS_LABELS[status]}
    </Badge>
  )
}
