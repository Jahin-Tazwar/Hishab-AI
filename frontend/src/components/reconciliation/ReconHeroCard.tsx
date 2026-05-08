import { Card, CardContent } from "@/components/ui/card"
import { formatBDT } from "@/lib/formatBDT"
import type { ReconciliationRow } from "@/types/reconciliation"

/**
 * Headline ITC numbers — Safe ITC, At-Risk ITC, Total VAT claimed.
 * The two ITC numbers are the actionable insight (safe = file with confidence,
 * at-risk = needs CA review). Compact lakh/crore formatting for at-a-glance.
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
        />
        <Stat
          label="At-risk ITC"
          value={formatBDT(atRisk, { compact: true })}
          subtext={formatBDT(atRisk)}
          tone="red"
        />
        <Stat
          label="Total VAT claimed"
          value={formatBDT(totalVat, { compact: true })}
          subtext={formatBDT(totalVat)}
          tone="slate"
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
  label, value, subtext, tone,
}: { label: string; value: string; subtext: string; tone: Tone }) {
  return (
    <div className="space-y-1">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`text-3xl font-semibold ${TONE[tone]}`}>{value}</p>
      <p className="text-xs text-slate-500">{subtext}</p>
    </div>
  )
}
