import { cn } from "@/lib/utils"

interface Props {
  half: "purchase_register" | "supplier_export"
  subState: "upload" | "extract" | "review" | "reused"
  filename?: string
  className?: string
}

const HALF_LABEL = {
  purchase_register: "Purchase register",
  supplier_export: "Supplier-filed export",
} as const

const SUB_LABEL = {
  upload: "Upload",
  extract: "Extracting",
  review: "Review",
  reused: "Reusing prior document",
} as const

/**
 * Small in-card banner shown above an active half's content. Tells the
 * user which half they're on and what sub-state ("Extracting", "Review",
 * etc.) — the top-of-page Stepper only shows the 5 high-level steps so
 * this fills in the detail.
 */
export function HalfHeader({ half, subState, filename, className }: Props) {
  return (
    <div className={cn("flex items-baseline gap-2 text-sm", className)}>
      <span className="font-medium text-foreground">{HALF_LABEL[half]}</span>
      <span className="text-muted-foreground" aria-hidden>·</span>
      <span className="text-muted-foreground">
        {SUB_LABEL[subState]}{filename ? ` (${filename})` : ""}
      </span>
    </div>
  )
}
