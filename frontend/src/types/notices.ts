import { z } from "zod"

export const NOTICE_STATUSES = [
  "pending", "parsing", "parsed", "awaiting_data", "ready_to_draft",
  "drafting", "drafted", "finalized", "failed",
] as const
export type NoticeStatus = (typeof NOTICE_STATUSES)[number]

export const NOTICE_TYPES = ["input_vat_mismatch", "unsupported"] as const
export type NoticeType = (typeof NOTICE_TYPES)[number]

export const DRAFT_STATUSES = ["draft", "under_review", "finalized"] as const
export type DraftStatus = (typeof DRAFT_STATUSES)[number]

const uuid = z.string().uuid()

export const noticeSchema = z.object({
  id: uuid,
  tenant_id: uuid,
  client_id: uuid,
  created_by: uuid,
  original_filename: z.string(),
  mime_type: z.string(),
  byte_size: z.number().int(),
  status: z.enum(NOTICE_STATUSES),
  parse_error: z.string().nullable().optional(),
  notice_no: z.string().nullable().optional(),
  notice_date: z.string().nullable().optional(),         // ISO date
  notice_type: z.enum(NOTICE_TYPES).nullable().optional(),
  taxpayer_bin: z.string().nullable().optional(),
  taxpayer_tin: z.string().nullable().optional(),
  period_start: z.string().nullable().optional(),
  period_end: z.string().nullable().optional(),
  alleged_itc_claimed_bdt: z.string().nullable().optional(),
  alleged_itc_allowed_bdt: z.string().nullable().optional(),
  alleged_shortfall_bdt: z.string().nullable().optional(),
  linked_reconciliation_id: uuid.nullable().optional(),
  linked_ingestion_job_id: uuid.nullable().optional(),
  created_at: z.string(),
  updated_at: z.string(),
})
export type Notice = z.infer<typeof noticeSchema>

export const citationSchema = z.object({
  corpus_chunk_id: uuid,
  source_ref: z.string(),
  snippet: z.string(),
  paragraph_idx: z.number().int(),
})
export type Citation = z.infer<typeof citationSchema>

export const appendixRowSchema = z.object({
  label: z.string(),
  value_bdt: z.string().nullable().optional(),
  note: z.string().nullable().optional(),
})
export type AppendixRow = z.infer<typeof appendixRowSchema>

export const appendixJsonSchema = z.object({
  rows: z.array(appendixRowSchema),
})
export type AppendixJson = z.infer<typeof appendixJsonSchema>

export const noticeDraftSchema = z.object({
  id: uuid,
  notice_id: uuid,
  language: z.string(),
  body_html: z.string(),
  appendix_json: appendixJsonSchema.passthrough(),
  citations: z.array(citationSchema),
  model_version: z.string(),
  status: z.enum(DRAFT_STATUSES),
  finalized_at: z.string().nullable().optional(),
  finalized_by: uuid.nullable().optional(),
  created_at: z.string(),
  updated_at: z.string(),
})
export type NoticeDraft = z.infer<typeof noticeDraftSchema>

export const linkedReconSchema = z.object({
  kind: z.literal("linked_recon"),
  reconciliation_id: uuid,
  client_id: uuid,
})
export const needsIngestionSchema = z.object({
  kind: z.literal("needs_ingestion"),
  client_id: uuid,
  period_start: z.string(),
  period_end: z.string(),
})
export const needsManualLinkSchema = z.object({
  kind: z.literal("needs_manual_link"),
  candidate_clients: z.array(uuid),
})
export const linkerResultSchema = z.discriminatedUnion("kind", [
  linkedReconSchema, needsIngestionSchema, needsManualLinkSchema,
])
export type LinkerResult = z.infer<typeof linkerResultSchema>
