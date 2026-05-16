import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { Stepper, statusToStep } from "@/components/ingestion/Stepper"

describe("statusToStep", () => {
  it.each([
    ["pending", 1],
    ["extracting", 2],
    ["ready_for_review", 3],
    ["confirmed", 4],
    ["reconciling", 4],
    ["completed", 4],
    ["failed", 4],
  ] as const)("maps %s to step %d", (status, step) => {
    expect(statusToStep(status as any)).toBe(step)
  })
})

describe("Stepper", () => {
  it("highlights the active step", () => {
    render(<Stepper activeStep={2} />)
    const items = screen.getAllByRole("listitem")
    expect(items).toHaveLength(4)
    expect(items[1]).toHaveAttribute("aria-current", "step")
  })
})
