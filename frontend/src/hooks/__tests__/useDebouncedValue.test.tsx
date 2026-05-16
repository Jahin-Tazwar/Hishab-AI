import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { useDebouncedValue } from "@/hooks/useDebouncedValue"

beforeEach(() => { vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers() })

describe("useDebouncedValue", () => {
  it("returns the latest value after the delay", () => {
    const { result, rerender } = renderHook(
      ({ v }: { v: string }) => useDebouncedValue(v, 250),
      { initialProps: { v: "a" } },
    )
    expect(result.current).toBe("a")
    rerender({ v: "abc" })
    expect(result.current).toBe("a")
    act(() => { vi.advanceTimersByTime(250) })
    expect(result.current).toBe("abc")
  })
})
