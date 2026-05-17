/**
 * Mirror of `backend/tests/reconciliation/test_buckets.py` — both sides must
 * agree on bucket assignment or the per-row badge will show a different
 * bucket than the headline KPIs reflect.
 */
import { describe, expect, it } from "vitest"

import { bucketReason, effectiveBucket, rowBucket } from "@/lib/reconciliation/buckets"
import type { ReconLineItemRow } from "@/types/reconciliation"

describe("effectiveBucket", () => {
  it.each([
    ["exact",    "safe"],
    ["fuzzy",    "safe"],
    ["partial",  "at_risk"],
    ["no_match", "at_risk"],
  ] as const)("no override → %s falls to %s", (status, expected) => {
    expect(effectiveBucket(status, null)).toBe(expected)
    expect(effectiveBucket(status, undefined)).toBe(expected)
  })

  it.each(["exact", "fuzzy", "partial", "no_match"] as const)(
    "approved override forces safe (was %s)", (status) => {
      expect(effectiveBucket(status, "approved")).toBe("safe")
    },
  )

  it.each(["exact", "fuzzy", "partial", "no_match"] as const)(
    "disputed override forces at_risk (was %s)", (status) => {
      expect(effectiveBucket(status, "disputed")).toBe("at_risk")
    },
  )

  it.each(["exact", "fuzzy", "partial", "no_match"] as const)(
    "ignore override excludes from totals (was %s)", (status) => {
      expect(effectiveBucket(status, "ignore")).toBe("ignored")
    },
  )
})

describe("rowBucket", () => {
  it("reads match_status and ca_override off the row", () => {
    const row = {
      match_status: "no_match",
      ca_override: "approved",
    } as unknown as ReconLineItemRow
    expect(rowBucket(row)).toBe("safe")
  })
})

describe("bucketReason", () => {
  it("explains a default safe row", () => {
    expect(bucketReason("exact", null)).toMatch(/Exact match/)
  })

  it("explains an overridden row", () => {
    expect(bucketReason("no_match", "approved")).toMatch(/You approved/)
  })

  it("explains an ignored row", () => {
    expect(bucketReason("fuzzy", "ignore")).toMatch(/excluded/)
  })
})
