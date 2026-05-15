import "@testing-library/jest-dom"
import { vi } from "vitest"

// next-themes (and many media-query hooks) call window.matchMedia on mount.
// jsdom does not implement it; provide a vi.fn()-backed stub so individual
// tests can spy on listeners or override mockImplementation when needed.
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})
