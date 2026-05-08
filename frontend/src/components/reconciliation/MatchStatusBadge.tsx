import { Badge } from "@/components/ui/badge"
import { MATCH_STATUS_LABELS, type MatchStatus } from "@/types/reconciliation"

const STYLE: Record<MatchStatus, string> = {
  exact: "bg-green-100 text-green-800 hover:bg-green-100",
  fuzzy: "bg-amber-100 text-amber-800 hover:bg-amber-100",
  partial: "bg-orange-100 text-orange-800 hover:bg-orange-100",
  no_match: "bg-red-100 text-red-800 hover:bg-red-100",
}

export function MatchStatusBadge({ status }: { status: MatchStatus }) {
  return (
    <Badge variant="secondary" className={STYLE[status]}>
      {MATCH_STATUS_LABELS[status]}
    </Badge>
  )
}
