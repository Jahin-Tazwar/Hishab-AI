/**
 * Mirror of `backend/app/reconciliation/buckets.py`.
 *
 * Single source of truth for which ITC bucket a recon line item contributes
 * to in the headline KPI totals. The frontend uses this for the per-row
 * badge in the table and the live preview in the drawer; the backend uses
 * the same logic when re-aggregating after a CA override.
 *
 * Priority:
 *   1. If `ca_override` is set, it wins:
 *      - "approved"  → "safe"
 *      - "disputed"  → "at_risk"
 *      - "ignore"    → "ignored" (excluded from both buckets)
 *   2. Otherwise, fall back to match_status:
 *      - exact / fuzzy   → "safe"
 *      - partial / no_match → "at_risk"
 */
import type { CAOverride, MatchStatus, ReconLineItemRow } from "@/types/reconciliation"

export type Bucket = "safe" | "at_risk" | "ignored"

const SAFE_MATCHES = new Set<MatchStatus>(["exact", "fuzzy"])

export function effectiveBucket(
  matchStatus: MatchStatus,
  caOverride: CAOverride | null | undefined,
): Bucket {
  if (caOverride === "approved") return "safe"
  if (caOverride === "disputed") return "at_risk"
  if (caOverride === "ignore") return "ignored"
  return SAFE_MATCHES.has(matchStatus) ? "safe" : "at_risk"
}

/** Convenience for the common "I have a row, give me its bucket" call site. */
export function rowBucket(item: ReconLineItemRow): Bucket {
  return effectiveBucket(item.match_status, item.ca_override)
}

export const BUCKET_LABELS: Record<Bucket, string> = {
  safe: "Safe ITC",
  at_risk: "At-risk ITC",
  ignored: "Ignored",
}

/**
 * Human-readable explanation for a row's bucket assignment. Used by the
 * drawer's live-preview pill so the CA understands why the row is in the
 * bucket it's in (and what changes if they pick a different override).
 */
export function bucketReason(
  matchStatus: MatchStatus,
  caOverride: CAOverride | null | undefined,
): string {
  if (caOverride === "approved") return "You approved this row, so it counts as Safe ITC."
  if (caOverride === "disputed") return "You disputed this row, so it counts as At-risk ITC."
  if (caOverride === "ignore")   return "You ignored this row, so it is excluded from the totals."
  if (matchStatus === "exact")    return "Exact match — counts as Safe ITC by default."
  if (matchStatus === "fuzzy")    return "Fuzzy match (BIN+invoice agree, minor date/amount drift) — counts as Safe ITC by default."
  if (matchStatus === "partial")  return "Partial match (BIN found in supplier export but invoice number doesn't line up) — counts as At-risk ITC by default."
  return "No match in the supplier-filed export — counts as At-risk ITC by default."
}
