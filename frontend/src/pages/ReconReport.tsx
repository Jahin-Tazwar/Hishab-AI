/**
 * Reconciliation report — hero ITC numbers, breakdown chart, line items table.
 * Path: /clients/:id/recon/:reconId
 */
import { useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { toast } from "sonner"

import { LineItemDrawer } from "@/components/reconciliation/LineItemDrawer"
import { ReconBreakdownChart } from "@/components/reconciliation/ReconBreakdownChart"
import { ReconHeroCard } from "@/components/reconciliation/ReconHeroCard"
import { ReconLineItemsTable } from "@/components/reconciliation/ReconLineItemsTable"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { PageLoading, Spinner } from "@/components/ui/Loading"
import { useClient } from "@/hooks/useClients"
import { useReconciliation, useReconLineItems } from "@/hooks/useReconciliations"
import {
  useComposeWorkingPaper, useWorkingPapersList,
} from "@/hooks/useWorkingPapers"
import { ApiError, api } from "@/lib/api"
import type { ReconLineItemRow } from "@/types/reconciliation"
import type { WorkingPaper } from "@/types/workingPapers"

export function ReconReport() {
  const { id: clientId, reconId } = useParams<{ id: string; reconId: string }>()
  const navigate = useNavigate()
  const { data: client } = useClient(clientId)
  const { data: recon, isLoading: reconLoading } = useReconciliation(reconId)
  const { data: items, isLoading: itemsLoading } = useReconLineItems(reconId)
  const workingPapers = useWorkingPapersList(clientId, "at_risk_itc_schedule")
  const compose = useComposeWorkingPaper(reconId ?? "")

  const [selected, setSelected] = useState<ReconLineItemRow | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [exporting, setExporting] = useState(false)

  const reconWorkingPapers: WorkingPaper[] = (workingPapers.data ?? [])
    .filter((wp) => wp.reconciliation_id === reconId)

  async function handleGenerateAtRiskItc() {
    if (!reconId || !clientId) return
    try {
      const out = await compose.mutateAsync("at_risk_itc_schedule")
      toast.success("Schedule generated.")
      navigate(`/clients/${clientId}/working-papers/${out.working_paper_id}`)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : (e as Error).message)
    }
  }

  function openDrawer(item: ReconLineItemRow) {
    setSelected(item)
    setDrawerOpen(true)
  }

  async function handleExport() {
    if (!reconId) return
    setExporting(true)
    try {
      const res = await api.get(`/api/v1/reconciliations/${reconId}/export`, {
        responseType: "blob",
      })
      const blob = new Blob([res.data], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      })
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `reconciliation-${reconId}.xlsx`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (e) {
      const msg = e instanceof ApiError ? e.message
        : e instanceof Error ? e.message : "Export failed"
      toast.error(msg)
    } finally {
      setExporting(false)
    }
  }

  if (reconLoading) {
    return <PageLoading label="Loading reconciliation…" />
  }

  if (!recon) {
    return (
      <div className="p-8 space-y-3">
        <p className="text-slate-700">Reconciliation not found.</p>
        <Link to={`/clients/${clientId}`} className="underline text-slate-900">
          Back to client
        </Link>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <Link to={`/clients/${clientId}`} className="text-sm text-slate-500 hover:underline">
            ← Back to {client?.name ?? "client"}
          </Link>
          <h1 className="text-2xl font-bold text-slate-900 mt-1">VAT reconciliation</h1>
          <p className="text-sm text-slate-600">
            Period: {recon.period_start} → {recon.period_end}
          </p>
          <p className="text-xs text-slate-500">
            Status: {recon.status} · {recon.total_invoices ?? 0} invoices
          </p>
        </div>
        <Button onClick={handleExport} disabled={exporting}>
          {exporting ? "Exporting…" : "Download XLSX"}
        </Button>
      </div>

      <ReconHeroCard recon={recon} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="text-base">Breakdown</CardTitle>
          </CardHeader>
          <CardContent>
            <ReconBreakdownChart recon={recon} />
            <div className="mt-3 grid grid-cols-2 gap-1 text-xs">
              <BreakRow label="Exact" value={recon.matched_exact ?? 0} />
              <BreakRow label="Fuzzy" value={recon.matched_fuzzy ?? 0} />
              <BreakRow label="Partial" value={recon.partial_match ?? 0} />
              <BreakRow label="No match" value={recon.no_match ?? 0} />
            </div>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">Line items</CardTitle>
          </CardHeader>
          <CardContent>
            {itemsLoading ? (
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <Spinner /> Loading line items…
              </div>
            ) : (
              <ReconLineItemsTable items={items ?? []} onSelect={openDrawer} />
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <CardTitle className="text-base">Working papers</CardTitle>
            <Button
              variant="outline"
              onClick={handleGenerateAtRiskItc}
              disabled={compose.isPending || !reconId}
            >
              {compose.isPending ? "Generating…" : "Generate At-Risk ITC Schedule"}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {reconWorkingPapers.length === 0 ? (
            <p className="text-sm text-slate-500">
              No working papers for this reconciliation yet. Generate an
              At-Risk ITC Schedule to surface suppliers needing follow-up.
            </p>
          ) : (
            <ul className="divide-y">
              {reconWorkingPapers.map((wp) => (
                <li key={wp.id} className="flex items-center justify-between py-2">
                  <Link
                    to={`/clients/${clientId}/working-papers/${wp.id}`}
                    className="text-sm font-medium text-slate-900 hover:underline"
                  >
                    At-Risk ITC Schedule
                  </Link>
                  <div className="flex items-center gap-3 text-xs text-slate-500">
                    <span>{new Date(wp.created_at).toLocaleString()}</span>
                    {wp.status === "finalized" ? (
                      <Badge variant="secondary">Finalized</Badge>
                    ) : (
                      <Badge variant="outline">Draft</Badge>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <LineItemDrawer item={selected} open={drawerOpen} onOpenChange={setDrawerOpen} />
    </div>
  )
}

function BreakRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex justify-between">
      <span className="text-slate-500">{label}</span>
      <span className="font-mono">{value}</span>
    </div>
  )
}
