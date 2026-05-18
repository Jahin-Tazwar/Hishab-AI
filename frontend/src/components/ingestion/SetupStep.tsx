import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"

import { PeriodPicker } from "@/components/reconciliation/PeriodPicker"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useStartSession } from "@/hooks/useIngestion"
import { usePriorDocs } from "@/hooks/usePriorDocs"
import { ApiError } from "@/lib/api"
import { notifyNoticeOfReconciliation } from "@/lib/notices/wizardCallback"

interface Props {
  clientId: string
}

export function SetupStep({ clientId }: Props) {
  const navigate = useNavigate()
  const startSession = useStartSession()

  const [period, setPeriod] = useState({ start: "", end: "" })
  const [reusePr, setReusePr] = useState(false)
  const [reuseSf, setReuseSf] = useState(false)

  const periodError = period.start && period.end && period.end < period.start
    ? "Period end must be on or after period start" : undefined
  const periodComplete = Boolean(period.start && period.end && !periodError)

  const prior = usePriorDocs(clientId, period.start, period.end)
  const priorPr = prior.data?.pr ?? null
  const priorSf = prior.data?.sf ?? null

  async function handleStart() {
    if (!periodComplete) return
    try {
      const res = await startSession.mutateAsync({
        client_id: clientId,
        period_start: period.start,
        period_end: period.end,
        reuse_pr_doc_id: reusePr && priorPr ? priorPr.id : undefined,
        reuse_sf_doc_id: reuseSf && priorSf ? priorSf.id : undefined,
      })
      if (res.reconciliation_id) {
        const noticeId = await notifyNoticeOfReconciliation({
          clientId,
          periodStart: period.start,
          periodEnd: period.end,
          reconciliationId: res.reconciliation_id,
        })
        if (noticeId) {
          toast.success("Reconciliation done — your reply draft is ready.")
          navigate(`/clients/${clientId}/notices/${noticeId}`, { replace: true })
          return
        }
        toast.success("Reconciliation complete")
        navigate(`/clients/${clientId}/recon/${res.reconciliation_id}`, { replace: true })
        return
      }
      // The wizard URL always points at whichever job exists (PR if any,
      // otherwise the SF job).
      const wizardJobId = res.pr_job_id ?? res.sf_job_id
      if (!wizardJobId) {
        toast.error("Session start returned no job id")
        return
      }
      navigate(`/clients/${clientId}/ingestion/${wizardJobId}`)
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e as Error).message
      toast.error(msg)
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader><CardTitle>Period</CardTitle></CardHeader>
        <CardContent>
          <PeriodPicker
            start={period.start}
            end={period.end}
            onChange={setPeriod}
            disabled={startSession.isPending}
            errorMessage={periodError}
          />
        </CardContent>
      </Card>

      {periodComplete && (priorPr || priorSf) && (
        <Card>
          <CardHeader><CardTitle>Reuse prior documents?</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {priorPr && (
              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={reusePr}
                  onChange={(e) => setReusePr(e.target.checked)}
                  disabled={startSession.isPending}
                  className="mt-1"
                />
                <span className="text-sm">
                  <span className="font-medium">Reuse purchase register</span>
                  <span className="block text-muted-foreground">
                    {priorPr.original_filename} · {new Date(priorPr.created_at).toLocaleDateString()}
                  </span>
                </span>
              </label>
            )}
            {priorSf && (
              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={reuseSf}
                  onChange={(e) => setReuseSf(e.target.checked)}
                  disabled={startSession.isPending}
                  className="mt-1"
                />
                <span className="text-sm">
                  <span className="font-medium">Reuse supplier-filed export</span>
                  <span className="block text-muted-foreground">
                    {priorSf.original_filename} · {new Date(priorSf.created_at).toLocaleDateString()}
                  </span>
                </span>
              </label>
            )}
          </CardContent>
        </Card>
      )}

      <div className="flex items-center gap-3">
        <Button
          onClick={handleStart}
          disabled={!periodComplete || startSession.isPending}
        >
          {startSession.isPending ? "Starting…" : "Start"}
        </Button>
      </div>
    </div>
  )
}
