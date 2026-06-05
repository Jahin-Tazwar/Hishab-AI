/**
 * Working Papers domain types + Zod schemas.
 *
 * Mirrors the backend Pydantic models in backend/app/working_papers/schemas.py.
 *
 * The `composed_json` shape is recipe-specific; today the only kind is
 * `at_risk_itc_schedule`. Each new kind adds its own discriminated payload
 * schema below.
 *
 * All monetary BDT amounts come down as strings (e.g. "50000.00") to avoid
 * floating-point precision loss. UI formatters parse them lazily.
 */
import { z } from "zod"

export const WORKING_PAPER_KINDS = ["at_risk_itc_schedule"] as const
export type WorkingPaperKind = (typeof WORKING_PAPER_KINDS)[number]

export const WORKING_PAPER_STATUSES = ["draft", "finalized"] as const
export type WorkingPaperStatus = (typeof WORKING_PAPER_STATUSES)[number]

export const WP_MATCH_STATUSES = [
  "exact", "fuzzy", "partial", "no_match",
] as const
export type WpMatchStatus = (typeof WP_MATCH_STATUSES)[number]

export const WP_CA_OVERRIDES = ["approved", "disputed", "ignore"] as const
export type WpCaOverride = (typeof WP_CA_OVERRIDES)[number]

export const RECOMMENDED_ACTIONS = [
  "chase_supplier", "reverse_claim", "partner_review",
  "approved_by_ca", "no_action",
] as const
export type RecommendedAction = (typeof RECOMMENDED_ACTIONS)[number]

export const RECOMMENDED_ACTION_LABELS: Record<RecommendedAction, string> = {
  chase_supplier: "Chase supplier",
  reverse_claim: "Reverse claim",
  partner_review: "Partner review",
  approved_by_ca: "Approved by CA",
  no_action: "No action",
}

export const WP_MATCH_STATUS_LABELS: Record<WpMatchStatus, string> = {
  exact: "Exact",
  fuzzy: "Fuzzy",
  partial: "Partial",
  no_match: "No match",
}

const uuid = z.string().uuid()

export const atRiskLineSchema = z.object({
  line_id: uuid,
  supplier_name: z.string().nullable().optional(),
  supplier_bin: z.string().nullable().optional(),
  invoice_no: z.string().nullable().optional(),
  invoice_date: z.string().nullable().optional(),
  taxable_amount_bdt: z.string().nullable().optional(),
  vat_amount_bdt: z.string().nullable().optional(),
  sf_taxable_amount_bdt: z.string().nullable().optional(),
  sf_vat_amount_bdt: z.string().nullable().optional(),
  vat_variance_bdt: z.string().nullable().optional(),
  discrepancy_reason: z.string().nullable().optional(),
  date_off_by_days: z.number().int().nullable().optional(),
  match_status: z.enum(WP_MATCH_STATUSES),
  match_score: z.string().nullable().optional(),
  ca_override: z.enum(WP_CA_OVERRIDES).nullable().optional(),
  ca_notes: z.string().nullable().optional(),
  recommended_action: z.enum(RECOMMENDED_ACTIONS),
})
export type AtRiskLine = z.infer<typeof atRiskLineSchema>

export const atRiskSupplierGroupSchema = z.object({
  supplier_name: z.string().nullable().optional(),
  supplier_bin: z.string().nullable().optional(),
  lines: z.array(atRiskLineSchema),
  total_vat_at_risk_bdt: z.string(),
  line_count: z.number().int(),
})
export type AtRiskSupplierGroup = z.infer<typeof atRiskSupplierGroupSchema>

export const atRiskSummarySchema = z.object({
  total_vat_claimed_bdt: z.string(),
  safe_itc_bdt: z.string(),
  at_risk_itc_bdt: z.string(),
  total_lines: z.number().int(),
  at_risk_line_count: z.number().int(),
  supplier_count_at_risk: z.number().int(),
})
export type AtRiskSummary = z.infer<typeof atRiskSummarySchema>

export const atRiskItcSchedulePayloadSchema = z.object({
  kind: z.literal("at_risk_itc_schedule"),
  recipe_version: z.string(),
  client_id: uuid,
  client_name: z.string(),
  client_bin: z.string().nullable().optional(),
  reconciliation_id: uuid,
  period_start: z.string(),
  period_end: z.string(),
  summary: atRiskSummarySchema,
  supplier_groups: z.array(atRiskSupplierGroupSchema),
})
export type AtRiskItcSchedulePayload = z.infer<typeof atRiskItcSchedulePayloadSchema>

export const workingPaperSchema = z.object({
  id: uuid,
  tenant_id: uuid,
  client_id: uuid,
  kind: z.enum(WORKING_PAPER_KINDS),
  reconciliation_id: uuid.nullable().optional(),
  period_start: z.string().nullable().optional(),
  period_end: z.string().nullable().optional(),
  recipe_version: z.string(),
  composed_json: z.record(z.unknown()),
  notes_html: z.string(),
  status: z.enum(WORKING_PAPER_STATUSES),
  finalized_at: z.string().nullable().optional(),
  finalized_by: uuid.nullable().optional(),
  composed_by: uuid,
  created_at: z.string(),
  updated_at: z.string(),
})
export type WorkingPaper = z.infer<typeof workingPaperSchema>

export const workingPaperRevisionSchema = z.object({
  id: uuid,
  revision_no: z.number().int(),
  edited_by: uuid,
  edit_source: z.enum([
    "recipe_composed", "user_edit", "recipe_regenerated",
  ]),
  edit_reason: z.string().nullable().optional(),
  created_at: z.string(),
})
export type WorkingPaperRevision = z.infer<typeof workingPaperRevisionSchema>
