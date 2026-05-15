import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ThemeProvider } from "next-themes"
import { describe, expect, it } from "vitest"

import { ThemeToggle } from "@/components/layout/ThemeToggle"

function renderWithTheme(ui: React.ReactNode) {
  return render(
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}>
      {ui}
    </ThemeProvider>,
  )
}

describe("ThemeToggle", () => {
  it("switches the document class on click", async () => {
    renderWithTheme(<ThemeToggle />)
    const btn = screen.getByRole("button", { name: /toggle theme/i })
    expect(document.documentElement.classList.contains("dark")).toBe(false)
    await userEvent.click(btn)
    expect(document.documentElement.classList.contains("dark")).toBe(true)
  })
})
