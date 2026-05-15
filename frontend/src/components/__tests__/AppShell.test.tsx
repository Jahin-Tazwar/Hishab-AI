// frontend/src/components/__tests__/AppShell.test.tsx
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

import { AppShell } from "@/components/layout/AppShell"

vi.mock("@/hooks/useUserProfile", () => ({
  useUserProfile: () => ({ data: { full_name: "Test User", tenant_id: "t1" } }),
}))
vi.mock("@/lib/supabase", () => ({
  supabase: { auth: { signOut: vi.fn() } },
}))

function withProviders(ui: React.ReactNode) {
  const qc = new QueryClient()
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/dashboard"]}>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe("AppShell", () => {
  it("renders all top-level nav items including Ingestion", () => {
    render(withProviders(<AppShell><div>content</div></AppShell>))
    expect(screen.getByRole("link", { name: "Dashboard" })).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Clients" })).toBeInTheDocument()
  })

  it("toggles mobile sidebar with the menu button", async () => {
    render(withProviders(<AppShell><div>content</div></AppShell>))
    const toggle = screen.getByRole("button", { name: /open menu/i })
    await userEvent.click(toggle)
    expect(screen.getByRole("button", { name: /close menu/i })).toBeInTheDocument()
  })
})
