import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"

import * as wpApi from "@/lib/working-papers/api"
import {
  useWorkingPaper, useWorkingPapersList,
} from "@/hooks/useWorkingPapers"

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  }
}

describe("useWorkingPapersList", () => {
  it("fetches when clientId given", async () => {
    vi.spyOn(wpApi, "listWorkingPapers").mockResolvedValueOnce([])
    const { result } = renderHook(
      () => useWorkingPapersList("c1"), { wrapper: wrapper() },
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual([])
  })

  it("is disabled when clientId is empty", async () => {
    vi.spyOn(wpApi, "listWorkingPapers").mockResolvedValueOnce([])
    const { result } = renderHook(
      () => useWorkingPapersList(undefined), { wrapper: wrapper() },
    )
    await new Promise((r) => setTimeout(r, 30))
    expect(result.current.fetchStatus).toBe("idle")
  })
})

describe("useWorkingPaper", () => {
  it("calls getWorkingPaper and returns the row", async () => {
    const row = {
      id: "wp1", tenant_id: "t", client_id: "c",
      kind: "at_risk_itc_schedule" as const,
      recipe_version: "v1", composed_json: {}, notes_html: "",
      status: "draft" as const, composed_by: "u",
      created_at: "x", updated_at: "x",
    }
    vi.spyOn(wpApi, "getWorkingPaper").mockResolvedValueOnce(row as any)
    const { result } = renderHook(
      () => useWorkingPaper("wp1"), { wrapper: wrapper() },
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data?.id).toBe("wp1")
  })
})
