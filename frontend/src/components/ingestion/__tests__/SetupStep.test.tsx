import { vi } from "vitest"

vi.mock("@/lib/supabase", () => ({
  supabase: { auth: { getSession: vi.fn().mockResolvedValue({ data: { session: null } }) } },
}))

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import MockAdapter from "axios-mock-adapter"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it } from "vitest"

import { SetupStep } from "@/components/ingestion/SetupStep"
import { api } from "@/lib/api"

let mock: MockAdapter
beforeEach(() => { mock = new MockAdapter(api) })
afterEach(() => { mock.restore() })

function withClient(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>
}

const CLIENT = "33333333-3333-3333-3333-333333333333"

describe("<SetupStep />", () => {
  it("does not show reuse offers when there are no prior docs", async () => {
    mock.onGet("/api/v1/ingestion/documents/recent").reply(200, { pr: null, sf: null })
    render(withClient(<SetupStep clientId={CLIENT} />))
    const start = await screen.findByLabelText("Period start")
    const end = await screen.findByLabelText("Period end")
    await userEvent.type(start, "2026-05-01")
    await userEvent.type(end, "2026-05-31")
    await waitFor(() => expect(mock.history.get.length).toBeGreaterThanOrEqual(1))
    expect(screen.queryByText(/Reuse prior documents/i)).not.toBeInTheDocument()
  })

  it("shows a reuse offer for an existing PR doc", async () => {
    mock.onGet("/api/v1/ingestion/documents/recent").reply(200, {
      pr: {
        id: "44444444-4444-4444-4444-444444444444",
        doc_type: "purchase_register",
        original_filename: "old-pr.xlsx",
        file_size_bytes: 1024,
        created_at: "2026-04-15T00:00:00+00:00",
      },
      sf: null,
    })
    render(withClient(<SetupStep clientId={CLIENT} />))
    await userEvent.type(screen.getByLabelText("Period start"), "2026-05-01")
    await userEvent.type(screen.getByLabelText("Period end"), "2026-05-31")
    await waitFor(() => expect(screen.getByText("old-pr.xlsx", { exact: false })).toBeInTheDocument())
    expect(screen.getByText(/Reuse purchase register/i)).toBeInTheDocument()
  })
})
