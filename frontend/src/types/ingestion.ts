import { z } from "zod"

export const JobKindEnum = z.enum(["purchase_register", "supplier_export"])
export type JobKind = z.infer<typeof JobKindEnum>

export const JobStatusEnum = z.enum([
  "pending", "extracting", "ready_for_review",
  "confirmed", "reconciling", "completed", "failed",
])
export type JobStatus = z.infer<typeof JobStatusEnum>

export const FileStatusEnum = z.enum([
  "queued", "extracting", "extracted", "failed", "skipped",
])
export type FileStatus = z.infer<typeof FileStatusEnum>

export const RowStatusEnum = z.enum([
  "auto_passed", "needs_review", "confirmed", "rejected", "edited",
])
export type RowStatus = z.infer<typeof RowStatusEnum>

const Uuid = z.string().uuid()
const IsoDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/)
const IsoDateTime = z.string()

// Decimals come from Pydantic as either strings (preferred) or numbers; coerce to string.
const Decimalish = z.union([
  z.string(),
  z.number().transform((n) => n.toFixed(2)),
])

export const FieldWarningSchema = z.object({
  field: z.string(),
  code: z.string(),
  message: z.string(),
})
export type FieldWarning = z.infer<typeof FieldWarningSchema>

export const ExtractedRowDataSchema = z.object({
  invoice_no: z.string(),
  invoice_date: IsoDate,
  taxable_amount_bdt: Decimalish,
  vat_amount_bdt: Decimalish,
  supplier_bin: z.string().nullable().optional(),
  supplier_name: z.string().nullable().optional(),
  buyer_bin: z.string().nullable().optional(),
})
export type ExtractedRowData = z.infer<typeof ExtractedRowDataSchema>

export const ExtractedRowOutSchema = z.object({
  id: Uuid,
  file_id: Uuid,
  job_id: Uuid,
  source_page_no: z.number().int().nullable().optional(),
  row_data: ExtractedRowDataSchema,
  row_data_original: ExtractedRowDataSchema,
  status: RowStatusEnum,
  field_warnings: z.array(FieldWarningSchema).default([]),
  reviewed_by: Uuid.nullable().optional(),
  reviewed_at: IsoDateTime.nullable().optional(),
  created_at: IsoDateTime,
})
export type ExtractedRowOut = z.infer<typeof ExtractedRowOutSchema>

export const JobOutSchema = z.object({
  id: Uuid,
  tenant_id: Uuid,
  client_id: Uuid,
  kind: JobKindEnum,
  period_start: IsoDate,
  period_end: IsoDate,
  status: JobStatusEnum,
  files_total: z.number().int(),
  files_done: z.number().int(),
  rows_total: z.number().int(),
  rows_needs_review: z.number().int(),
  error_summary: z.string().nullable().optional(),
  reconciliation_id: Uuid.nullable().optional(),
  linked_pr_job_id: Uuid.nullable().optional(),
  linked_sf_job_id: Uuid.nullable().optional(),
  reuse_pr_doc_id: Uuid.nullable().optional(),
  reuse_sf_doc_id: Uuid.nullable().optional(),
  created_at: IsoDateTime,
  updated_at: IsoDateTime,
  completed_at: IsoDateTime.nullable().optional(),
})
export type JobOut = z.infer<typeof JobOutSchema>

export const IngestionFileOutSchema = z.object({
  id: Uuid,
  job_id: Uuid,
  original_filename: z.string(),
  mime_type: z.string(),
  byte_size: z.number().int(),
  engine: z.string().nullable().optional(),
  status: FileStatusEnum,
  rows_extracted: z.number().int(),
  needs_review: z.boolean(),
  warnings: z.array(z.record(z.unknown())).default([]),
  error: z.string().nullable().optional(),
  extracted_at: IsoDateTime.nullable().optional(),
})
export type IngestionFileOut = z.infer<typeof IngestionFileOutSchema>

export const JobDetailOutSchema = z.object({
  job: JobOutSchema,
  files: z.array(IngestionFileOutSchema),
})
export type JobDetailOut = z.infer<typeof JobDetailOutSchema>

export const RowsListOutSchema = z.object({
  rows: z.array(ExtractedRowOutSchema),
  total: z.number().int(),
  has_more: z.boolean(),
})
export type RowsListOut = z.infer<typeof RowsListOutSchema>

export const CreateJobFileSummarySchema = z.object({
  file_id: Uuid,
  original_filename: z.string(),
  mime_type: z.string(),
  byte_size: z.number().int(),
  accepted: z.boolean(),
  rejection_reason: z.string().nullable().optional(),
})
export type CreateJobFileSummary = z.infer<typeof CreateJobFileSummarySchema>

export const CreateJobResponseSchema = z.object({
  job_id: Uuid,
  files: z.array(CreateJobFileSummarySchema),
})
export type CreateJobResponse = z.infer<typeof CreateJobResponseSchema>

export const FinalizeResponseSchema = z.object({
  reconciliation_id: Uuid,
})
export type FinalizeResponse = z.infer<typeof FinalizeResponseSchema>

// ── Session start ─────────────────────────────────────────────────────────

export const SessionStartRequestSchema = z.object({
  client_id: Uuid,
  period_start: IsoDate,
  period_end: IsoDate,
  reuse_pr_doc_id: Uuid.nullable().optional(),
  reuse_sf_doc_id: Uuid.nullable().optional(),
})
export type SessionStartRequest = z.infer<typeof SessionStartRequestSchema>

export const SessionStartResponseSchema = z.object({
  pr_job_id: Uuid.nullable().optional(),
  sf_job_id: Uuid.nullable().optional(),
  reconciliation_id: Uuid.nullable().optional(),
})
export type SessionStartResponse = z.infer<typeof SessionStartResponseSchema>

// ── Recent documents ──────────────────────────────────────────────────────

export const RecentDocSchema = z.object({
  id: Uuid,
  doc_type: z.enum(["purchase_register", "supplier_export"]),
  original_filename: z.string(),
  file_size_bytes: z.number().int().nullable().optional(),
  created_at: IsoDateTime,
})
export type RecentDoc = z.infer<typeof RecentDocSchema>

export const RecentDocsOutSchema = z.object({
  pr: RecentDocSchema.nullable().optional(),
  sf: RecentDocSchema.nullable().optional(),
})
export type RecentDocsOut = z.infer<typeof RecentDocsOutSchema>
