import { describe, expect, it } from "vitest"

import {
  atRiskItcSchedulePayloadSchema,
  atRiskLineSchema,
  WORKING_PAPER_KINDS,
  WORKING_PAPER_STATUSES,
  workingPaperSchema,
} from "@/types/workingPapers"

const UUID = "11111111-1111-1111-1111-111111111111"

describe("workingPaperSchema", () => {
  it("parses a draft row with composed_json kept as a record", () => {
    const out = workingPaperSchema.safeParse({
      id: UUID,
      tenant_id: UUID,
      client_id: UUID,
      kind: "at_risk_itc_schedule",
      reconciliation_id: UUID,
      period_start: "2026-04-01",
      period_end: "2026-04-30",
      recipe_version: "v1",
      composed_json: { kind: "at_risk_itc_schedule", anything: 42 },
      notes_html: "<p></p>",
      status: "draft",
      composed_by: UUID,
      created_at: "2026-05-18T00:00:00Z",
      updated_at: "2026-05-18T00:00:00Z",
    })
    expect(out.success).toBe(true)
    expect(out.data?.status).toBe("draft")
  })

  it("rejects unknown status values", () => {
    const bad = workingPaperSchema.safeParse({
      id: UUID,
      tenant_id: UUID,
      client_id: UUID,
      kind: "at_risk_itc_schedule",
      recipe_version: "v1",
      composed_json: {},
      notes_html: "",
      status: "weird",
      composed_by: UUID,
      created_at: "2026-05-18T00:00:00Z",
      updated_at: "2026-05-18T00:00:00Z",
    })
    expect(bad.success).toBe(false)
  })
})

describe("atRiskLineSchema", () => {
  it("requires match_status and recommended_action enums", () => {
    const ok = atRiskLineSchema.safeParse({
      line_id: UUID,
      supplier_name: "ACME",
      supplier_bin: null,
      invoice_no: "INV-1",
      invoice_date: "2026-04-15",
      taxable_amount_bdt: "10000.00",
      vat_amount_bdt: "1500.00",
      match_status: "no_match",
      match_score: null,
      ca_override: null,
      ca_notes: null,
      recommended_action: "chase_supplier",
    })
    expect(ok.success).toBe(true)

    const bad = atRiskLineSchema.safeParse({
      ...ok.data!,
      recommended_action: "explode",
    })
    expect(bad.success).toBe(false)
  })
})

describe("atRiskItcSchedulePayloadSchema", () => {
  it("parses a full payload with one supplier group", () => {
    const payload = {
      kind: "at_risk_itc_schedule" as const,
      recipe_version: "v1",
      client_id: UUID,
      client_name: "Test Co Ltd",
      client_bin: "001234567-0101",
      reconciliation_id: UUID,
      period_start: "2026-04-01",
      period_end: "2026-04-30",
      summary: {
        total_vat_claimed_bdt: "50000.00",
        safe_itc_bdt: "30000.00",
        at_risk_itc_bdt: "20000.00",
        total_lines: 10,
        at_risk_line_count: 4,
        supplier_count_at_risk: 2,
      },
      supplier_groups: [{
        supplier_name: "ACME",
        supplier_bin: null,
        lines: [],
        total_vat_at_risk_bdt: "5000.00",
        line_count: 0,
      }],
    }
    expect(atRiskItcSchedulePayloadSchema.parse(payload).client_name)
      .toBe("Test Co Ltd")
  })
})

describe("constants", () => {
  it("exposes the at_risk_itc_schedule kind and draft/finalized statuses", () => {
    expect(WORKING_PAPER_KINDS).toContain("at_risk_itc_schedule")
    expect(new Set(WORKING_PAPER_STATUSES))
      .toEqual(new Set(["draft", "finalized"]))
  })
})
