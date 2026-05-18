import { describe, expect, it } from "vitest"

import {
  NOTICE_STATUSES,
  noticeSchema,
  noticeDraftSchema,
  linkerResultSchema,
} from "@/types/notices"

describe("noticeSchema", () => {
  it("rejects unknown status values", () => {
    const ok = noticeSchema.safeParse({
      id: "11111111-1111-1111-1111-111111111111",
      tenant_id: "11111111-1111-1111-1111-111111111111",
      client_id: "11111111-1111-1111-1111-111111111111",
      created_by: "11111111-1111-1111-1111-111111111111",
      original_filename: "n.pdf",
      mime_type: "application/pdf",
      byte_size: 1024,
      status: "pending",
      created_at: "2026-05-18T00:00:00Z",
      updated_at: "2026-05-18T00:00:00Z",
    })
    expect(ok.success).toBe(true)

    const bad = noticeSchema.safeParse({ ...ok.data!, status: "weird" })
    expect(bad.success).toBe(false)
  })
})

describe("linkerResultSchema", () => {
  it("discriminates by kind", () => {
    const lr = linkerResultSchema.parse({
      kind: "linked_recon",
      reconciliation_id: "11111111-1111-1111-1111-111111111111",
      client_id: "11111111-1111-1111-1111-111111111112",
    })
    expect(lr.kind).toBe("linked_recon")

    const ni = linkerResultSchema.parse({
      kind: "needs_ingestion",
      client_id: "11111111-1111-1111-1111-111111111112",
      period_start: "2026-04-01",
      period_end: "2026-04-30",
    })
    expect(ni.kind).toBe("needs_ingestion")
  })
})

describe("NOTICE_STATUSES", () => {
  it("exposes the same 9 statuses as the backend enum", () => {
    expect(new Set(NOTICE_STATUSES)).toEqual(new Set([
      "pending","parsing","parsed","awaiting_data","ready_to_draft",
      "drafting","drafted","finalized","failed",
    ]))
  })
})

describe("noticeDraftSchema", () => {
  it("parses citations array shape", () => {
    const ok = noticeDraftSchema.safeParse({
      id: "11111111-1111-1111-1111-111111111111",
      notice_id: "11111111-1111-1111-1111-111111111111",
      language: "bn",
      body_html: "<p>hi</p>",
      appendix_json: { rows: [] },
      citations: [{
        corpus_chunk_id: "11111111-1111-1111-1111-111111111111",
        source_ref: "Section 46",
        snippet: "…",
        paragraph_idx: 0,
      }],
      model_version: "g25",
      status: "draft",
      created_at: "2026-05-18T00:00:00Z",
      updated_at: "2026-05-18T00:00:00Z",
    })
    expect(ok.success).toBe(true)
  })
})
