import { AlertTriangle } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import type { FieldWarning } from "@/types/ingestion"

const HUMAN: Record<string, string> = {
  BIN_MISSING: "BIN missing",
  BIN_FORMAT: "BIN format invalid",
  DATE_OUT_OF_PERIOD: "Date outside period",
  VAT_RATIO_UNUSUAL: "VAT % outside 4-16%",
}

export function WarningChip({ warning }: { warning: FieldWarning }) {
  const label = HUMAN[warning.code] ?? warning.code
  return (
    <Badge variant="outline" className="gap-1 border-amber-400/60 text-amber-700 dark:text-amber-300">
      <AlertTriangle className="size-3" aria-hidden />
      <span title={warning.message}>{label}</span>
    </Badge>
  )
}
