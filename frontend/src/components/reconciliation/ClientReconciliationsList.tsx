import { Link } from "react-router-dom"

import { buttonVariants } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import { useClientReconciliations } from "@/hooks/useReconciliations"
import { formatBDT } from "@/lib/formatBDT"

interface Props {
  clientId: string
}

export function ClientReconciliationsList({ clientId }: Props) {
  const { data, isLoading } = useClientReconciliations(clientId)

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base">VAT reconciliations</CardTitle>
        <Link to={`/clients/${clientId}/recon/new`} className={buttonVariants()}>
          New reconciliation
        </Link>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="text-sm text-slate-500">Loading…</p>
        ) : !data || data.length === 0 ? (
          <p className="text-sm text-slate-500">
            No reconciliations yet. Run one to see Safe ITC and at-risk numbers.
          </p>
        ) : (
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Period</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Invoices</TableHead>
                  <TableHead className="text-right">Safe ITC</TableHead>
                  <TableHead className="text-right">At-risk ITC</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell>{r.period_start} → {r.period_end}</TableCell>
                    <TableCell className="text-slate-600">{r.status}</TableCell>
                    <TableCell className="text-right font-mono">{r.total_invoices ?? 0}</TableCell>
                    <TableCell className="text-right font-mono">
                      {formatBDT(r.safe_itc_bdt, { symbol: false })}
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {formatBDT(r.at_risk_itc_bdt, { symbol: false })}
                    </TableCell>
                    <TableCell>
                      <Link
                        to={`/clients/${clientId}/recon/${r.id}`}
                        className="text-sm text-slate-900 underline"
                      >
                        View
                      </Link>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
