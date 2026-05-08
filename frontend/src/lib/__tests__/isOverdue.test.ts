import { describe, expect, it } from "vitest"

import { isOverdue } from "../isOverdue"

const today = new Date("2024-06-10")

describe("isOverdue", () => {
  it("is true for pending events past due", () => {
    expect(isOverdue({ status: "pending", due_date: "2024-06-09" }, today)).toBe(true)
  })

  it("is false for pending events due today", () => {
    expect(isOverdue({ status: "pending", due_date: "2024-06-10" }, today)).toBe(false)
  })

  it("is false for pending events due in the future", () => {
    expect(isOverdue({ status: "pending", due_date: "2024-06-11" }, today)).toBe(false)
  })

  it("is false for filed events even past due", () => {
    expect(isOverdue({ status: "filed", due_date: "2024-06-01" }, today)).toBe(false)
  })

  it("is false for waived events", () => {
    expect(isOverdue({ status: "waived", due_date: "2024-06-01" }, today)).toBe(false)
  })

  it("is false for na events", () => {
    expect(isOverdue({ status: "na", due_date: "2024-06-01" }, today)).toBe(false)
  })
})
