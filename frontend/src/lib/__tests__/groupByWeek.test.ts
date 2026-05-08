import { describe, expect, it } from "vitest"

import { groupByWeek } from "../groupByWeek"

interface T { due_date: string }

const today = new Date("2024-06-10") // Monday

describe("groupByWeek", () => {
  it("returns empty buckets for empty input", () => {
    const r = groupByWeek<T>([], today, (e) => e.due_date)
    expect(r.thisWeek).toEqual([])
    expect(r.nextWeek).toEqual([])
    expect(r.weeksThreeAndFour).toEqual([])
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

  it("places weeks 3 and 4 (days 14-27 from today) in weeksThreeAndFour", () => {
    const r = groupByWeek<T>(
      [{ due_date: "2024-06-24" }, { due_date: "2024-07-07" }],
      today,
      (e) => e.due_date,
    )
    // Jun 24 = day 14 → weeksThreeAndFour
    // Jul 7  = day 27 → weeksThreeAndFour
    expect(r.weeksThreeAndFour).toHaveLength(2)
  })

  it("ignores past dates and dates beyond 28 days", () => {
    const r = groupByWeek<T>(
      [{ due_date: "2024-06-09" }, { due_date: "2024-07-09" }],
      today,
      (e) => e.due_date,
    )
    expect(r.thisWeek).toHaveLength(0)
    expect(r.nextWeek).toHaveLength(0)
    expect(r.weeksThreeAndFour).toHaveLength(0)
  })
})
