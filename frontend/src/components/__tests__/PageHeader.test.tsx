import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"

import { Breadcrumbs } from "@/components/layout/Breadcrumbs"
import { PageHeader } from "@/components/layout/PageHeader"

describe("PageHeader", () => {
  it("renders title, subtitle, and actions slot", () => {
    render(
      <MemoryRouter>
        <PageHeader
          title="My title"
          subtitle="My subtitle"
          actions={<button>Do thing</button>}
        />
      </MemoryRouter>,
    )
    expect(screen.getByRole("heading", { level: 1, name: "My title" })).toBeInTheDocument()
    expect(screen.getByText("My subtitle")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Do thing" })).toBeInTheDocument()
  })
})

describe("Breadcrumbs", () => {
  it("renders trail with terminal item un-linked", () => {
    render(
      <MemoryRouter>
        <Breadcrumbs items={[
          { label: "Clients", to: "/clients" },
          { label: "Acme Textiles", to: "/clients/abc" },
          { label: "New ingestion" },
        ]} />
      </MemoryRouter>,
    )
    expect(screen.getByRole("link", { name: "Clients" })).toHaveAttribute("href", "/clients")
    expect(screen.getByRole("link", { name: "Acme Textiles" })).toHaveAttribute("href", "/clients/abc")
    expect(screen.getByText("New ingestion").tagName).toBe("SPAN")
  })
})
