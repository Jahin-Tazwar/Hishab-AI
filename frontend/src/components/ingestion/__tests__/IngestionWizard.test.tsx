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

function withClient(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>
}

const PR_ID = "11111111-1111-1111-1111-111111111111"
const SF_ID = "22222222-2222-2222-2222-222222222222"
const CLIENT_ID = "33333333-3333-3333-3333-333333333333"

function jobJson(over: Record<string, unknown>) {
  return {
    id: PR_ID, tenant_id: PR_ID, client_id: CLIENT_ID,
    kind: "purchase_register", period_start: "2026-05-01", period_end: "2026-05-31",
    status: "ready_for_review",
    files_total: 1, files_done: 1, rows_total: 4, rows_needs_review: 0,
    error_summary: null, reconciliation_id: null,
    linked_pr_job_id: null, linked_sf_job_id: null,
    reuse_pr_doc_id: null, reuse_sf_doc_id: null,
    created_at: "2026-05-15T00:00:00+00:00",
    updated_at: "2026-05-15T00:00:00+00:00",
    completed_at: null,
    ...over,
  }
}

describe("<IngestionWizard /> step routing", () => {
  it("renders the PurchaseHalf review when PR is ready_for_review with no SF", async () => {
    mock.onGet(`/api/v1/ingestion/jobs/${PR_ID}`).reply(200, {
      job: jobJson({}),
      files: [],
    })
    mock.onGet(`/api/v1/ingestion/jobs/${PR_ID}/rows`).reply(200, { rows: [], total: 0, has_more: false })
    render(withClient(<IngestionWizard prJobId={PR_ID} clientId={CLIENT_ID} />))
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /continue to supplier export/i }))
        .toBeInTheDocument(),
    )
    // Both Stepper and HalfHeader contain "Purchase register" — at least one must exist.
    expect(screen.getAllByText("Purchase register").length).toBeGreaterThan(0)
  })

  it("renders SupplierHalf upload when PR is confirmed and no SF exists", async () => {
    mock.onGet(`/api/v1/ingestion/jobs/${PR_ID}`).reply(200, {
      job: jobJson({ status: "confirmed", linked_sf_job_id: null }),
      files: [],
    })
    render(withClient(<IngestionWizard prJobId={PR_ID} clientId={CLIENT_ID} />))
    // "Supplier-filed export" is unique to the HalfHeader (Stepper uses "Supplier export").
    await waitFor(() => expect(screen.getByText("Supplier-filed export")).toBeInTheDocument())
    // HalfHeader sub-state label "Upload" confirms we're on the upload step.
    expect(screen.getByText("Upload")).toBeInTheDocument()
  })

  it("fetches the linked SF job and shows FinalizeStep when SF is confirmed", async () => {
    mock.onGet(`/api/v1/ingestion/jobs/${PR_ID}`).reply(200, {
      job: jobJson({ status: "confirmed", linked_sf_job_id: SF_ID }),
      files: [],
    })
    mock.onGet(`/api/v1/ingestion/jobs/${SF_ID}`).reply(200, {
      job: jobJson({ id: SF_ID, kind: "supplier_export", status: "confirmed", linked_pr_job_id: PR_ID }),
      files: [],
    })
    render(withClient(<IngestionWizard prJobId={PR_ID} clientId={CLIENT_ID} />))
    await waitFor(() => expect(screen.getByText(/Ready to finalize/i)).toBeInTheDocument())
  })
})
