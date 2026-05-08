import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it } from "vitest"

import { NotFound } from "../NotFound"
import { useAuthStore } from "@/store/auth"

describe("NotFound", () => {
  beforeEach(() => {
    useAuthStore.setState({ session: null, user: null, isLoading: false })
  })

  it("shows 'Back to dashboard' when authenticated", () => {
    useAuthStore.setState({
      // @ts-expect-error -- partial Session is fine for this test
      session: { access_token: "x", user: { id: "u" } },
      // @ts-expect-error -- partial User is fine for this test
      user: { id: "u" },
      isLoading: false,
    })
    render(
      <MemoryRouter>
        <NotFound />
      </MemoryRouter>,
    )
    expect(screen.getByText(/page not found/i)).toBeInTheDocument()
    const link = screen.getByRole("link", { name: /back to dashboard/i })
    expect(link).toHaveAttribute("href", "/dashboard")
  })

  it("shows 'Back to login' when unauthenticated", () => {
    render(
      <MemoryRouter>
        <NotFound />
      </MemoryRouter>,
    )
    const link = screen.getByRole("link", { name: /back to login/i })
    expect(link).toHaveAttribute("href", "/login")
  })
})
