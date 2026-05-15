import { describe, expect, it } from "vitest"

import {
  CreateJobResponseSchema,
  ExtractedRowDataSchema,
  JobDetailOutSchema,
  JobKindEnum,
  JobStatusEnum,
  RowStatusEnum,
} from "@/types/ingestion"

describe("ingestion schemas", () => {
  it("parses a valid CreateJobResponse", () => {
    const parsed = CreateJobResponseSchema.parse({
      job_id: "00000000-0000-0000-0000-000000000001",
      files: [
        {
          file_id: "00000000-0000-0000-0000-000000000002",
          original_filename: "x.xlsx",
          mime_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          byte_size: 1234,
          accepted: true,
          rejection_reason: null,
        },
      ],
    })
    expect(parsed.files).toHaveLength(1)
  })

  it("accepts string Decimals for amounts", () => {
    const parsed = ExtractedRowDataSchema.parse({
      invoice_no: "INV-1",
      invoice_date: "2026-05-15",
      taxable_amount_bdt: "1000.00",
      vat_amount_bdt: "150.00",
      supplier_bin: "100200300",
      supplier_name: "ACME",
      buyer_bin: null,
    })
    expect(parsed.taxable_amount_bdt).toBe("1000.00")
  })

  it("validates job status enum", () => {
    expect(JobStatusEnum.parse("ready_for_review")).toBe("ready_for_review")
    expect(() => JobStatusEnum.parse("bogus")).toThrow()
  })

  it("validates row status enum", () => {
    expect(RowStatusEnum.parse("auto_passed")).toBe("auto_passed")
  })

  it("parses JobDetailOut with files", () => {
    const parsed = JobDetailOutSchema.parse({
      job: {
        id: "00000000-0000-0000-0000-000000000001",
        tenant_id: "00000000-0000-0000-0000-000000000010",
        client_id: "00000000-0000-0000-0000-000000000020",
        kind: "purchase_register",
        period_start: "2026-05-01",
        period_end: "2026-05-31",
        status: "extracting",
        files_total: 1, files_done: 0,
        rows_total: 0, rows_needs_review: 0,
        error_summary: null, reconciliation_id: null,
        created_at: "2026-05-15T12:00:00+00:00",
        updated_at: "2026-05-15T12:00:00+00:00",
        completed_at: null,
      },
      files: [],
    })
    expect(parsed.job.status).toBe("extracting")
  })

  it("rejects invalid job kind", () => {
    expect(() => JobKindEnum.parse("vat_register")).toThrow()
  })
})
