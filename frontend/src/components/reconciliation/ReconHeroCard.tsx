import { Info } from "lucide-react"

import { Card, CardContent } from "@/components/ui/card"
import { formatBDT } from "@/lib/formatBDT"
import type { ReconciliationRow } from "@/types/reconciliation"

const SAFE_TOOLTIP =
  "Sum of VAT on rows the matcher classified as Exact or Fuzzy, plus any rows you've marked Approved. CAs marking a row Disputed or Ignore subtract from this total."
const AT_RISK_TOOLTIP =
  "Sum of VAT on rows the matcher classified as Partial or No-match, plus any rows you've marked Disputed. Marking a row Approved or Ignore reduces this number."
const TOTAL_TOOLTIP =
  "Safe + At-risk. Rows you've marked Ignore are excluded entirely, so the total reflects the VAT that's actually being claimed."

/**
 * Headline ITC numbers — Safe ITC, At-Risk ITC, Total VAT claimed.
 * The two ITC numbers are the actionable insight (safe = file with confidence,
 * at-risk = needs CA review). Compact lakh/crore formatting for at-a-glance;
 * the small info icons reveal the bucketing rule + how CA overrides affect it.
 */
export function ReconHeroCard({ recon }: { recon: ReconciliationRow }) {
  const safe = recon.safe_itc_bdt ?? "0"
  const atRisk = recon.at_risk_itc_bdt ?? "0"
  const totalVat = recon.total_vat_claimed_bdt ?? "0"

  return (
    <Card>
      <CardContent className="grid grid-cols-1 gap-6 md:grid-cols-3 py-6">
        <Stat
          label="Safe ITC"
          value={formatBDT(safe, { compact: true })}
          subtext={formatBDT(safe)}
          tone="green"
          tooltip={SAFE_TOOLTIP}
        />
        <Stat
          label="At-risk ITC"
          value={formatBDT(atRisk, { compact: true })}
          subtext={formatBDT(atRisk)}
          tone="red"
          tooltip={AT_RISK_TOOLTIP}
        />
        <Stat
          label="Total VAT claimed"
          value={formatBDT(totalVat, { compact: true })}
          subtext={formatBDT(totalVat)}
          tone="slate"
          tooltip={TOTAL_TOOLTIP}
        />
      </CardContent>
    </Card>
  )
}

type Tone = "green" | "red" | "slate"
const TONE: Record<Tone, string> = {
  green: "text-green-700",
  red: "text-red-700",
  slate: "text-slate-900",
}

function Stat({
  label, value, subtext, tone, tooltip,
}: { label: string; value: string; subtext: string; tone: Tone; tooltip?: string }) {
  return (
    <div className="space-y-1">
      <p className="flex items-center gap-1.5 text-xs uppercase tracking-wide text-slate-500">
        {label}
        {tooltip && (
          // Native title attribute gives a tooltip without pulling in a
          // Radix tooltip primitive. Adequate for an explanatory hint that
          // most users will never need.
          <span title={tooltip} className="cursor-help text-slate-400 hover:text-slate-600">
            <Info className="size-3" aria-label={`About ${label}`} />
          </span>
        )}
      </p>
      <p className={`text-3xl font-semibold ${TONE[tone]}`}>{value}</p>
      <p className="text-xs text-slate-500">{subtext}</p>
    </div>
  )
}
