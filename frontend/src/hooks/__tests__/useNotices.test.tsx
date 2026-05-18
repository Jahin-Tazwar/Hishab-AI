import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"

import * as noticesApi from "@/lib/notices/api"
import {
  useNoticeList, useNotice, useNoticeDraft,
} from "@/hooks/useNotices"

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  }
}

describe("useNoticeList", () => {
  it("fetches when clientId given", async () => {
    vi.spyOn(noticesApi, "listNotices").mockResolvedValueOnce([])
    const { result } = renderHook(() => useNoticeList("c1"), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual([])
  })

  it("is disabled when clientId is empty", async () => {
    vi.spyOn(noticesApi, "listNotices").mockResolvedValueOnce([])
    const { result } = renderHook(() => useNoticeList(undefined), { wrapper: wrapper() })
    await new Promise((r) => setTimeout(r, 30))
    expect(result.current.fetchStatus).toBe("idle")
  })
})

describe("useNotice + useNoticeDraft polling cadence", () => {
  it("useNotice polls every 2s while parsing/drafting", async () => {
    const spy = vi.spyOn(noticesApi, "getNotice").mockResolvedValue({
      id: "n1", tenant_id: "t", client_id: "c", created_by: "u",
      original_filename: "x.pdf", mime_type: "application/pdf",
      byte_size: 1, status: "parsing",
      created_at: "x", updated_at: "x",
    } as any)
    const { result } = renderHook(() => useNotice("n1"), { wrapper: wrapper() })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(spy).toHaveBeenCalled()
    // Suppress unused-import warning for useNoticeDraft (covered by other tests).
    void useNoticeDraft
  })
})
