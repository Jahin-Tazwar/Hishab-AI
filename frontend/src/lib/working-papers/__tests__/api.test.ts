import { describe, expect, it, vi } from "vitest"

import { api } from "@/lib/api"
import * as wpApi from "@/lib/working-papers/api"

vi.mock("@/lib/api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
  },
}))

const UUID = "11111111-1111-1111-1111-111111111111"

describe("working-papers api", () => {
  it("composeWorkingPaper posts the kind + reconciliation_id JSON", async () => {
    ;(api.post as any).mockResolvedValueOnce({ data: { working_paper_id: "wp1" } })
    const out = await wpApi.composeWorkingPaper({
      kind: "at_risk_itc_schedule", reconciliation_id: UUID,
    })
    expect(out.working_paper_id).toBe("wp1")
    expect(api.post).toHaveBeenCalledWith(
      "/api/v1/working-papers/",
      { kind: "at_risk_itc_schedule", reconciliation_id: UUID },
    )
  })

  it("composeWorkingPaper posts notice_id for an audit_defense_pack", async () => {
    ;(api.post as any).mockResolvedValueOnce({ data: { working_paper_id: "wp2" } })
    await wpApi.composeWorkingPaper({
      kind: "audit_defense_pack", notice_id: "n-1",
    })
    expect(api.post).toHaveBeenCalledWith(
      "/api/v1/working-papers/",
      { kind: "audit_defense_pack", notice_id: "n-1" },
    )
  })

  it("evidenceBundleUrl points at the bundle endpoint", () => {
    expect(wpApi.evidenceBundleUrl("wp-1"))
      .toContain("/api/v1/working-papers/wp-1/evidence-bundle")
  })

  it("listWorkingPapers filters by client_id + kind and parses through Zod", async () => {
    ;(api.get as any).mockResolvedValueOnce({ data: [{
      id: UUID,
      tenant_id: UUID,
      client_id: UUID,
      kind: "at_risk_itc_schedule",
      recipe_version: "v1",
      composed_json: {},
      notes_html: "",
      status: "draft",
      composed_by: UUID,
      created_at: "2026-05-18T00:00:00Z",
      updated_at: "2026-05-18T00:00:00Z",
      garbage: "should be dropped",
    }]})
    const out = await wpApi.listWorkingPapers(UUID, "at_risk_itc_schedule")
    expect(out).toHaveLength(1)
    expect((out[0] as any).garbage).toBeUndefined()
    const [path] = (api.get as any).mock.calls[0]
    expect(path).toContain(`client_id=${UUID}`)
    expect(path).toContain("kind=at_risk_itc_schedule")
  })

  it("updateWorkingPaperNotes hits the /notes endpoint with notes_html", async () => {
    ;(api.put as any).mockResolvedValueOnce({ data: { ok: true } })
    await wpApi.updateWorkingPaperNotes("wp1", "<p>hello</p>")
    expect(api.put).toHaveBeenCalledWith(
      "/api/v1/working-papers/wp1/notes",
      { notes_html: "<p>hello</p>" },
    )
  })

  it("exportWorkingPaperUrl builds a docx/pdf path with the format query", () => {
    expect(wpApi.exportWorkingPaperUrl("wp1", "docx"))
      .toBe("/api/v1/working-papers/wp1/export?format=docx")
    expect(wpApi.exportWorkingPaperUrl("wp1", "pdf"))
      .toBe("/api/v1/working-papers/wp1/export?format=pdf")
  })

  it("reopenWorkingPaper posts the reason in the body", async () => {
    ;(api.post as any).mockResolvedValueOnce({ data: { ok: true } })
    await wpApi.reopenWorkingPaper("wp1", "supplier disputed")
    expect(api.post).toHaveBeenCalledWith(
      "/api/v1/working-papers/wp1/reopen",
      { reason: "supplier disputed" },
    )
  })
})
