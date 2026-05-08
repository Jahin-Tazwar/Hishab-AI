// frontend/src/lib/obligationLabels.ts
/**
 * Display labels for the 6 seeded obligation types.
 * See migrations/0008_seed_obligations.sql for the source of truth.
 *
 * Falls back to a humanised version of the raw type for any unknown
 * obligation_type encountered (defensive — schema can grow).
 */
const LABELS: Record<string, string> = {
  vat_return: "VAT Return (Mushak 9.1)",
  tds_return: "TDS Return",
  tds_deposit: "TDS Challan Deposit",
  income_tax_company: "Company Income Tax Return",
  income_tax_individual: "Individual Income Tax Return",
  rjsc_annual: "RJSC Annual Return",
}

export function obligationLabel(type: string): string {
  if (LABELS[type]) return LABELS[type]
  // Unknown → humanise: "foo_bar_baz" → "Foo Bar Baz"
  return type
    .split("_")
    .map((w) => (w.length ? w[0].toUpperCase() + w.slice(1) : w))
    .join(" ")
}
