/**
 * Reconciliation domain types and Zod schemas.
 *
 * Mirrors the backend Pydantic models in backend/app/reconciliation/schemas.py.
 * Numeric BDT amounts are kept as strings on the wire to avoid float
 * precision loss; the UI parses them via Number(...) only at render time.
 */
import { z } from "zod"

// ── Enums ────────────────────────────────────────────────────────────────

export const MATCH_STATUSES = ["exact", "fuzzy", "partial", "no_match"] as const
export type MatchStatus = (typeof MATCH_STATUSES)[number]

export const CA_OVERRIDES = ["approved", "disputed", "ignore"] as const
export type CAOverride = (typeof CA_OVERRIDES)[number]

export const MATCH_STATUS_LABELS: Record<MatchStatus, string> = {
  exact: "Exact",
  fuzzy: "Fuzzy",
  partial: "Partial",
  no_match: "No match",
}

// ── Inbound / outbound API shapes ────────────────────────────────────────

/**
 * Form input — what the New Reconciliation page collects.
 * period_start / period_end are kept as ISO date strings (YYYY-MM-DD)
 * to round-trip cleanly with the FastAPI date type.
 */
export const reconciliationCreateSchema = z
  .object({
    client_id: z.string().uuid(),
    period_start: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "YYYY-MM-DD"),
    period_end: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "YYYY-MM-DD"),
    purchase_register_doc_id: z.string().uuid(),
    supplier_data_doc_id: z.string().uuid(),
  })
  .refine(
    (v) => v.period_end >= v.period_start,
    { message: "Period end must be on or after period start", path: ["period_end"] },
  )

export type ReconciliationCreateInput = z.infer<typeof reconciliationCreateSchema>

export interface ReconciliationCreateResponse {
  reconciliation_id: string
}

// ── DB row shapes (returned by Supabase select) ──────────────────────────

export interface ReconciliationRow {
  id: string
  tenant_id: string
  client_id: string
  period_start: string
  period_end: string
  status: "running" | "completed" | "error"
  total_invoices: number | null
  matched_exact: number | null
  matched_fuzzy: number | null
  partial_match: number | null
  no_match: number | null
  total_vat_claimed_bdt: string | null
  safe_itc_bdt: string | null
  at_risk_itc_bdt: string | null
  purchase_register_doc_id: string | null
  supplier_data_doc_id: string | null
  notes: string | null
  run_by: string
  started_at: string
  completed_at: string | null
}

export interface DiscrepancyFlags {
  date_off_by_days?: number | null
  amount_diff_bdt?: string | null
  amount_diff_pct?: number | null
  reason?: string | null
}

export interface ReconLineItemRow {
  id: string
  tenant_id: string
  reconciliation_id: string
  pr_invoice_no: string | null
  pr_supplier_bin: string | null
  pr_supplier_name: string | null
  pr_invoice_date: string | null
  pr_taxable_amount_bdt: string | null
  pr_vat_amount_bdt: string | null
  sf_invoice_no: string | null
  sf_invoice_date: string | null
  sf_taxable_amount_bdt: string | null
  sf_vat_amount_bdt: string | null
  match_status: MatchStatus
  match_score: string | null
  discrepancy_flags: DiscrepancyFlags | null
  ca_override: CAOverride | null
  ca_notes: string | null
  created_at: string
}
