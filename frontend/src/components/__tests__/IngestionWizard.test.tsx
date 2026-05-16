import { vi } from "vitest"

vi.mock("@/lib/supabase", () => ({
  supabase: { auth: { getSession: vi.fn().mockResolvedValue({ data: { session: null } }) } },
}))

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import MockAdapter from "axios-mock-adapter"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it } from "vitest"

import { IngestionWizard } from "@/components/ingestion/IngestionWizard"
import { api } from "@/lib/api"

let mock: MockAdapter
beforeEach(() => { mock = new MockAdapter(api) })
afterEach(() => { mock.restore() })

function withProviders(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

const JOB_ID = "00000000-0000-0000-0000-000000000001"
const CLIENT_ID = "00000000-0000-0000-0000-000000000010"

function jobFixture(status: string) {
  return {
    job: {
      id: JOB_ID, tenant_id: CLIENT_ID, client_id: CLIENT_ID,
      kind: "purchase_register", period_start: "2026-05-01", period_end: "2026-05-31",
      status,
      files_total: 1, files_done: 1,
      rows_total: 0, rows_needs_review: 0,
      error_summary: null, reconciliation_id: null,
      created_at: "2026-05-15T12:00:00+00:00",
      updated_at: "2026-05-15T12:00:00+00:00",
      completed_at: null,
    },
    files: [],
  }
}

describe("IngestionWizard", () => {
  it("renders ExtractingStep when status=extracting", async () => {
    mock.onGet(`/api/v1/ingestion/jobs/${JOB_ID}`).reply(200, jobFixture("extracting"))
    render(withProviders(<IngestionWizard jobId={JOB_ID} clientId={CLIENT_ID} />))
    await waitFor(() => expect(screen.getByText(/Extracting…/i)).toBeInTheDocument())
  })

  it("renders ReviewStep when status=ready_for_review", async () => {
    mock.onGet(`/api/v1/ingestion/jobs/${JOB_ID}`).reply(200, jobFixture("ready_for_review"))
    mock.onGet(`/api/v1/ingestion/jobs/${JOB_ID}/rows`).reply(200, { rows: [], total: 0, has_more: false })
    render(withProviders(<IngestionWizard jobId={JOB_ID} clientId={CLIENT_ID} />))
    await waitFor(() => expect(screen.getByText(/Review extracted rows/i)).toBeInTheDocument())
  })

  it("renders FinalizeStep when status=confirmed", async () => {
    mock.onGet(`/api/v1/ingestion/jobs/${JOB_ID}`).reply(200, jobFixture("confirmed"))
    render(withProviders(<IngestionWizard jobId={JOB_ID} clientId={CLIENT_ID} />))
    await waitFor(() => expect(screen.getByText(/Ready to finalize/i)).toBeInTheDocument())
  })
})
