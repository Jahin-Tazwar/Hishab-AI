import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"

import { ErrorBoundary } from "../ErrorBoundary"

function Throws() {
  throw new Error("kaboom")
}

function Maybe({ throws }: { throws: boolean }) {
  if (throws) throw new Error("kaboom")
  return <p>safe</p>
}

describe("ErrorBoundary", () => {
  it("renders children when no error", () => {
    render(
      <MemoryRouter>
        <ErrorBoundary>
          <p>hello</p>
        </ErrorBoundary>
      </MemoryRouter>,
    )
    expect(screen.getByText("hello")).toBeInTheDocument()
  })

  it("renders fallback when child throws", () => {
    // Suppress React's expected console.error for the throw
    const orig = console.error
    console.error = () => {}
    render(
      <MemoryRouter>
        <ErrorBoundary>
          <Throws />
        </ErrorBoundary>
      </MemoryRouter>,
    )
    console.error = orig
    expect(screen.getByText("Something went wrong")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument()
  })

  it("recovers when 'Try again' is clicked and child no longer throws", () => {
    const orig = console.error
    console.error = () => {}
    let throws = true
    function Wrapper() {
      return (
        <ErrorBoundary>
          <Maybe throws={throws} />
        </ErrorBoundary>
      )
    }
    const { rerender } = render(
      <MemoryRouter>
        <Wrapper />
      </MemoryRouter>,
    )
    expect(screen.getByText("Something went wrong")).toBeInTheDocument()

    throws = false
    fireEvent.click(screen.getByRole("button", { name: /try again/i }))
    rerender(
      <MemoryRouter>
        <Wrapper />
      </MemoryRouter>,
    )
    console.error = orig
    expect(screen.getByText("safe")).toBeInTheDocument()
  })
})
