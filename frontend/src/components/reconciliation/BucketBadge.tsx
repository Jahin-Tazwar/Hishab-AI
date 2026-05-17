import { ShieldAlert, ShieldCheck, ShieldOff } from "lucide-react"

import { cn } from "@/lib/utils"
import { BUCKET_LABELS, type Bucket } from "@/lib/reconciliation/buckets"

interface Props {
  bucket: Bucket
  /** Compact = icon + short label; full = label only. Defaults to compact. */
  variant?: "compact" | "full"
  className?: string
  title?: string
}

const STYLES: Record<Bucket, string> = {
  safe:    "bg-green-50 text-green-700 ring-green-200",
  at_risk: "bg-red-50 text-red-700 ring-red-200",
  ignored: "bg-slate-100 text-slate-600 ring-slate-200",
}

const ICONS: Record<Bucket, typeof ShieldCheck> = {
  safe: ShieldCheck,
  at_risk: ShieldAlert,
  ignored: ShieldOff,
}

/**
 * Colored pill showing which bucket a row contributes to: Safe ITC (green),
 * At-risk ITC (red), or Ignored (gray). Used in the line items table column
 * and the drawer's live preview.
 */
export function BucketBadge({ bucket, variant = "compact", className, title }: Props) {
  const Icon = ICONS[bucket]
  return (
    <span
      title={title ?? BUCKET_LABELS[bucket]}
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
        STYLES[bucket],
        className,
      )}
    >
      {variant === "compact" && <Icon className="size-3" aria-hidden />}
      {BUCKET_LABELS[bucket]}
    </span>
  )
}
