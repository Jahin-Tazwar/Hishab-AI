import { Badge } from "@/components/ui/badge"
import type { RowStatus } from "@/types/ingestion"

const STYLES: Record<RowStatus, string> = {
  auto_passed: "bg-muted text-foreground",
  needs_review: "bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-200",
  confirmed: "bg-green-100 text-green-900 dark:bg-green-900/40 dark:text-green-200",
  rejected: "bg-red-100 text-red-900 dark:bg-red-900/40 dark:text-red-200",
  edited: "bg-blue-100 text-blue-900 dark:bg-blue-900/40 dark:text-blue-200",
}

const LABELS: Record<RowStatus, string> = {
  auto_passed: "Auto",
  needs_review: "Needs review",
  confirmed: "Confirmed",
  rejected: "Rejected",
  edited: "Edited",
}

export function StatusChip({ status }: { status: RowStatus }) {
  return <Badge className={STYLES[status]}>{LABELS[status]}</Badge>
}
