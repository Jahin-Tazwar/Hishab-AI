// frontend/src/components/compliance/RecentReconciliationsWidget.tsx
import { Link } from "react-router-dom"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useRecentReconciliations } from "@/hooks/useCompliance"
import { formatBDT } from "@/lib/formatBDT"

export function RecentReconciliationsWidget() {
  const { data, isLoading } = useRecentReconciliations(5)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Recent reconciliations</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="text-sm text-slate-500">Loading…</p>
        ) : !data || data.length === 0 ? (
          <p className="text-sm text-slate-500">No reconciliations yet.</p>
        ) : (
          <ul className="divide-y rounded-md border">
            {data.map((r) => (
              <li
                key={r.id}
                className="flex items-center justify-between gap-3 px-3 py-2"
              >
                <div className="min-w-0 flex-1">
                  <Link
                    to={`/clients/${r.client_id}/recon/${r.id}`}
                    className="text-sm font-medium text-slate-900 hover:underline"
                  >
                    {r.client_name}
                  </Link>
                  <p className="text-xs text-slate-500">
                    {r.period_start} → {r.period_end}
                  </p>
                </div>
                <span className="font-mono text-xs text-red-700">
                  {formatBDT(r.at_risk_itc_bdt, { compact: true })} at risk
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
