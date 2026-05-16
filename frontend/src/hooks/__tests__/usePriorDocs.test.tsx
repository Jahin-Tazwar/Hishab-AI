import { vi } from "vitest"

vi.mock("@/lib/supabase", () => ({
  supabase: { auth: { getSession: vi.fn().mockResolvedValue({ data: { session: null } }) } },
}))

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor } from "@testing-library/react"
import MockAdapter from "axios-mock-adapter"
import { afterEach, beforeEach, describe, expect, it } from "vitest"

import { usePriorDocs } from "@/hooks/usePriorDocs"
import { api } from "@/lib/api"

let mock: MockAdapter
function wrapper(qc: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  }
}

beforeEach(() => { mock = new MockAdapter(api) })
afterEach(() => { mock.restore() })

const CLIENT = "11111111-1111-1111-1111-111111111111"

describe("usePriorDocs", () => {
  it("is disabled when params are missing", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => usePriorDocs(undefined, "", ""), { wrapper: wrapper(qc) })
    expect(result.current.fetchStatus).toBe("idle")
  })

  it("returns parsed pr+sf when API responds", async () => {
    mock.onGet("/api/v1/ingestion/documents/recent").reply(200, {
      pr: {
        id: "22222222-2222-2222-2222-222222222222",
        doc_type: "purchase_register",
        original_filename: "pr.xlsx",
        file_size_bytes: 1024,
        created_at: "2026-05-10T00:00:00+00:00",
      },
      sf: null,
    })
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(
      () => usePriorDocs(CLIENT, "2026-05-01", "2026-05-31"),
      { wrapper: wrapper(qc) },
    )
    await waitFor(() => expect(result.current.data?.pr?.original_filename).toBe("pr.xlsx"))
    expect(result.current.data?.sf).toBeNull()
  })
})
