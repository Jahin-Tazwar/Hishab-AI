import { describe, expect, it } from "vitest"

import { groupByWeek } from "../groupByWeek"

interface T { due_date: string }

const today = new Date("2024-06-10") // Monday

describe("groupByWeek", () => {
  it("returns empty buckets for empty input", () => {
    const r = groupByWeek<T>([], today, (e) => e.due_date)
    expect(r.thisWeek).toEqual([])
    expect(r.nextWeek).toEqual([])
    expect(r.laterThisMonth).toEqual([])
  })

  it("places today in thisWeek", () => {
    const r = groupByWeek<T>([{ due_date: "2024-06-10" }], today, (e) => e.due_date)
    expect(r.thisWeek).toHaveLength(1)
  })

  it("places end-of-this-week in thisWeek (Sunday boundary)", () => {
    // Mon-start week: Mon Jun 10 → Sun Jun 16 inclusive
    const r = groupByWeek<T>([{ due_date: "2024-06-16" }], today, (e) => e.due_date)
    expect(r.thisWeek).toHaveLength(1)
    expect(r.nextWeek).toHaveLength(0)
  })

  it("places start-of-next-week in nextWeek", () => {
    const r = groupByWeek<T>([{ due_date: "2024-06-17" }], today, (e) => e.due_date)
    expect(r.thisWeek).toHaveLength(0)
    expect(r.nextWeek).toHaveLength(1)
  })

  it("places days 14-30 from today in laterThisMonth", () => {
    const r = groupByWeek<T>(
      [
        { due_date: "2024-06-24" }, // day 14
        { due_date: "2024-07-07" }, // day 27
        { due_date: "2024-07-10" }, // day 30 — formerly dropped, now included
      ],
      today,
      (e) => e.due_date,
    )
    expect(r.laterThisMonth).toHaveLength(3)
  })

  it("ignores past dates and dates beyond 30 days", () => {
    const r = groupByWeek<T>(
      [
        { due_date: "2024-06-09" }, // yesterday
        { due_date: "2024-07-11" }, // day 31
      ],
      today,
      (e) => e.due_date,
    )
    expect(r.thisWeek).toHaveLength(0)
    expect(r.nextWeek).toHaveLength(0)
    expect(r.laterThisMonth).toHaveLength(0)
  })
})
