/**
 * Format an amount in Bangladeshi Taka using the South-Asian
 * lakh / crore digit grouping (e.g. 12,34,56,789.50).
 *
 * Accepts numbers or numeric strings (the wire format from the backend
 * preserves precision via strings). null/undefined returns "—".
 *
 * Default precision is 2 decimal places. Pass `compact: true` for a
 * lakh/crore suffixed form ("৳12.35 cr") for headlines.
 */
export interface FormatBDTOptions {
  decimals?: number
  /** Add the "৳" prefix. Default true. */
  symbol?: boolean
  /** Use lakh/crore suffixes for big numbers (1L+, 1Cr+). Default false. */
  compact?: boolean
}

const NBSP = " " // keep symbol attached to value

function _parse(value: number | string | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null
  const n = typeof value === "number" ? value : Number(value)
  return Number.isFinite(n) ? n : null
}

/**
 * Format the integer part with comma at every 2 digits (after the first 3).
 * 12345678 → "1,23,45,678"
 */
function _groupSouthAsian(intStr: string): string {
  const negative = intStr.startsWith("-")
  let digits = negative ? intStr.slice(1) : intStr
  if (digits.length <= 3) return (negative ? "-" : "") + digits

  const last3 = digits.slice(-3)
  const rest = digits.slice(0, -3)
  // Group remaining digits in twos from the right
  const grouped = rest.replace(/\B(?=(\d{2})+(?!\d))/g, ",")
  return (negative ? "-" : "") + grouped + "," + last3
}

export function formatBDT(
  value: number | string | null | undefined,
  opts: FormatBDTOptions = {},
): string {
  const { decimals = 2, symbol = true, compact = false } = opts
  const n = _parse(value)
  if (n === null) return "—"

  const sign = n < 0 ? "-" : ""
  const abs = Math.abs(n)
  const symPart = symbol ? `৳${NBSP}` : ""

  if (compact) {
    if (abs >= 1e7) {
      const cr = (abs / 1e7).toFixed(2)
      return `${sign}${symPart}${cr}${NBSP}cr`
    }
    if (abs >= 1e5) {
      const lk = (abs / 1e5).toFixed(2)
      return `${sign}${symPart}${lk}${NBSP}L`
    }
  }

  const fixed = abs.toFixed(decimals)
  const [intPart, decPart] = fixed.split(".")
  const grouped = _groupSouthAsian(intPart)
  const tail = decimals > 0 && decPart ? `.${decPart}` : ""
  return `${sign}${symPart}${grouped}${tail}`
}
