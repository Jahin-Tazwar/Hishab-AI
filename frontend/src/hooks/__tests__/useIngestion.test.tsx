// frontend/src/hooks/__tests__/useIngestion.test.tsx
import { vi } from "vitest"

vi.mock("@/lib/supabase", () => ({
  supabase: { auth: { getSession: vi.fn().mockResolvedValue({ data: { session: null } }) } },
}))

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor } from "@testing-library/react"
import MockAdapter from "axios-mock-adapter"
import { afterEach, beforeEach, describe, expect, it } from "vitest"

import { useJob, useJobRows } from "@/hooks/useIngestion"
import { api } from "@/lib/api"

let mock: MockAdapter
function wrapper(qc: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  }
}

beforeEach(() => { mock = new MockAdapter(api) })
afterEach(() => { mock.restore() })

const JOB_ID = "00000000-0000-0000-0000-000000000001"

describe("useJob", () => {
  it("returns parsed JobDetailOut on success", async () => {
    mock.onGet(`/api/v1/ingestion/jobs/${JOB_ID}`).reply(200, {
      job: {
        id: JOB_ID, tenant_id: JOB_ID, client_id: JOB_ID,
        kind: "purchase_register", period_start: "2026-05-01", period_end: "2026-05-31",
        status: "ready_for_review",
        files_total: 1, files_done: 1, rows_total: 0, rows_needs_review: 0,
        error_summary: null, reconciliation_id: null,
        created_at: "2026-05-15T12:00:00+00:00",
        updated_at: "2026-05-15T12:00:00+00:00",
        completed_at: null,
      },
      files: [],
    })
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => useJob(JOB_ID), { wrapper: wrapper(qc) })
    await waitFor(() => expect(result.current.data?.job.status).toBe("ready_for_review"))
  })
})

describe("useJobRows", () => {
  it("returns rows for the configured filter", async () => {
    mock.onGet(`/api/v1/ingestion/jobs/${JOB_ID}/rows`, { params: { filter: "needs_review", limit: 200, offset: 0 } })
      .reply(200, { rows: [], total: 0, has_more: false })
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => useJobRows(JOB_ID, "needs_review"), { wrapper: wrapper(qc) })
    await waitFor(() => expect(result.current.data?.total).toBe(0))
  })
})
