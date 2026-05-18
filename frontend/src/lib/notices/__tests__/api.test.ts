import { describe, expect, it, vi } from "vitest"

import { api } from "@/lib/api"
import * as noticesApi from "@/lib/notices/api"

vi.mock("@/lib/api", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
  },
}))

describe("notices api", () => {
  it("uploadNotice posts multipart with client_id", async () => {
    ;(api.post as any).mockResolvedValueOnce({ data: { notice_id: "n1" } })
    const file = new File([new Uint8Array(10)], "x.pdf", { type: "application/pdf" })
    const out = await noticesApi.uploadNotice("c1", file)
    expect(out.notice_id).toBe("n1")
    const [path, body] = (api.post as any).mock.calls[0]
    expect(path).toMatch(/\/notices\/?\?client_id=c1$/)
    expect(body).toBeInstanceOf(FormData)
  })

  it("relink posts JSON body with period and optional recon id", async () => {
    ;(api.post as any).mockResolvedValueOnce({ data: { ok: true } })
    await noticesApi.relinkNotice("n1", {
      client_id: "11111111-1111-1111-1111-111111111111",
      period_start: "2026-04-01",
      period_end: "2026-04-30",
      reconciliation_id: "22222222-2222-2222-2222-222222222222",
    })
    expect(api.post).toHaveBeenCalledWith(
      "/api/v1/notices/n1/relink",
      expect.objectContaining({ reconciliation_id: "22222222-2222-2222-2222-222222222222" }),
    )
  })

  it("listNotices parses through Zod and drops unexpected fields", async () => {
    ;(api.get as any).mockResolvedValueOnce({ data: [{
      id: "11111111-1111-1111-1111-111111111111",
      tenant_id: "11111111-1111-1111-1111-111111111111",
      client_id: "11111111-1111-1111-1111-111111111111",
      created_by: "11111111-1111-1111-1111-111111111111",
      original_filename: "n.pdf",
      mime_type: "application/pdf",
      byte_size: 1,
      status: "pending",
      created_at: "2026-05-18T00:00:00Z",
      updated_at: "2026-05-18T00:00:00Z",
      garbage: "ignored",
    }]})
    const out = await noticesApi.listNotices("c1")
    expect(out).toHaveLength(1)
    expect((out[0] as any).garbage).toBeUndefined()
  })
})
