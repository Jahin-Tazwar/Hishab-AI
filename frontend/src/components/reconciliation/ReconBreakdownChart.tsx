import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts"

import type { ReconciliationRow } from "@/types/reconciliation"

/**
 * Donut showing the four match-status counts. Colour scheme matches
 * MatchStatusBadge so the palette is consistent across the report.
 */
const COLORS = {
  exact: "#16a34a",     // green-600
  fuzzy: "#d97706",     // amber-600
  partial: "#ea580c",   // orange-600
  no_match: "#dc2626",  // red-600
} as const

export function ReconBreakdownChart({ recon }: { recon: ReconciliationRow }) {
  const data = [
    { name: "Exact",   value: recon.matched_exact ?? 0,  fill: COLORS.exact },
    { name: "Fuzzy",   value: recon.matched_fuzzy ?? 0,  fill: COLORS.fuzzy },
    { name: "Partial", value: recon.partial_match ?? 0,  fill: COLORS.partial },
    { name: "No match",value: recon.no_match ?? 0,       fill: COLORS.no_match },
  ].filter((d) => d.value > 0)

  if (data.length === 0) {
    return (
      <div className="flex h-60 items-center justify-center text-sm text-slate-500">
        No invoices matched yet.
      </div>
    )
  }

  return (
    <div className="h-60 w-full">
      <ResponsiveContainer>
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            innerRadius={50}
            outerRadius={80}
            paddingAngle={2}
          >
            {data.map((entry) => (
              <Cell key={entry.name} fill={entry.fill} />
            ))}
          </Pie>
          <Tooltip />
          <Legend verticalAlign="bottom" iconType="circle" />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
