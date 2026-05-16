import { vi } from "vitest"

vi.mock("@/lib/supabase", () => ({
  supabase: { auth: { getSession: vi.fn().mockResolvedValue({ data: { session: null } }) } },
}))

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"

import { FinalizeStep } from "@/components/ingestion/FinalizeStep"
import type { JobOut } from "@/types/ingestion"

function job(overrides: Partial<JobOut> = {}): JobOut {
  return {
    id: "j1", tenant_id: "t", client_id: "c", kind: "supplier_export",
    period_start: "2026-05-01", period_end: "2026-05-31",
    status: "confirmed",
    files_total: 1, files_done: 1, rows_total: 4, rows_needs_review: 0,
    error_summary: null, reconciliation_id: null,
    linked_pr_job_id: null, linked_sf_job_id: null,
    reuse_pr_doc_id: null, reuse_sf_doc_id: null,
    created_at: "2026-05-15T00:00:00+00:00",
    updated_at: "2026-05-15T00:00:00+00:00",
    completed_at: null,
    ...overrides,
  } as JobOut
}

function withClient(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe("<FinalizeStep />", () => {
  it("renders the error banner when status=confirmed and error_summary is set", () => {
    render(withClient(
      <FinalizeStep
        job={job({ status: "confirmed", error_summary: "BOOM" })}
        clientId="c"
      />,
    ))
    expect(screen.getByText(/Last attempt failed/i)).toBeInTheDocument()
    expect(screen.getByText("BOOM")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /run reconciliation/i })).toBeInTheDocument()
  })

  it("does not render the banner on a clean confirmed job", () => {
    render(withClient(
      <FinalizeStep
        job={job({ status: "confirmed", error_summary: null })}
        clientId="c"
      />,
    ))
    expect(screen.queryByText(/Last attempt failed/i)).not.toBeInTheDocument()
  })
})
