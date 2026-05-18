// frontend/src/components/ingestion/FinalizeStep.tsx
import { AlertTriangle, CheckCircle2, Loader2, XCircle } from "lucide-react"
import { useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useFinalize } from "@/hooks/useIngestion"
import { notifyNoticeOfReconciliation } from "@/lib/notices/wizardCallback"
import type { JobOut } from "@/types/ingestion"

interface Props {
  job: JobOut
  clientId: string
  /** Override the job whose `finalize` endpoint gets called. Defaults to `job.id`.
   *  Set this when the wizard is showing the SF job but finalize should target the PR job, or vice versa. */
  finalizeJobId?: string
}

export function FinalizeStep({ job, clientId, finalizeJobId }: Props) {
  const navigate = useNavigate()
  const targetId = finalizeJobId ?? job.id
  const finalize = useFinalize(targetId)

  // Auto-navigate when reconciliation completes
  useEffect(() => {
    if (job.status === "completed" && job.reconciliation_id) {
      const reconciliationId = job.reconciliation_id
      void (async () => {
        const noticeId = await notifyNoticeOfReconciliation({
          clientId,
          periodStart: job.period_start,
          periodEnd: job.period_end,
          reconciliationId,
        })
        if (noticeId) {
          toast.success("Reconciliation done — your reply draft is ready.")
          navigate(`/clients/${clientId}/notices/${noticeId}`, { replace: true })
          return
        }
        toast.success("Reconciliation complete")
        navigate(`/clients/${clientId}/recon/${reconciliationId}`, { replace: true })
      })()
    }
  }, [job.status, job.reconciliation_id, job.period_start, job.period_end, clientId, navigate])

  async function handleFinalize() {
    try {
      await finalize.mutateAsync()
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  if (job.status === "reconciling") {
    return (
      <Card>
        <CardHeader><CardTitle>Reconciling…</CardTitle></CardHeader>
        <CardContent>
          <div className="flex items-center gap-3 text-sm">
            <Loader2 className="size-5 animate-spin text-primary" aria-hidden />
            <p>Matching invoices against the supplier-filed export.</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (job.status === "completed") {
    return (
      <Card>
        <CardHeader><CardTitle>Done</CardTitle></CardHeader>
        <CardContent className="flex items-center gap-3 text-sm">
          <CheckCircle2 className="size-5 text-green-600 dark:text-green-500" aria-hidden />
          <p>Redirecting to the reconciliation report…</p>
        </CardContent>
      </Card>
    )
  }

  if (job.status === "failed") {
    return (
      <Card>
        <CardHeader><CardTitle>Reconciliation failed</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center gap-3 text-sm">
            <XCircle className="size-5 text-destructive" aria-hidden />
            <p>{job.error_summary || "An unexpected error occurred."}</p>
          </div>
          <Button onClick={handleFinalize} disabled={finalize.isPending}>
            Retry
          </Button>
        </CardContent>
      </Card>
    )
  }

  // status === "confirmed": ready to finalize, optionally with a previous-attempt error banner.
  return (
    <Card>
      <CardHeader><CardTitle>Ready to finalize</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        {job.error_summary && (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm"
          >
            <AlertTriangle className="size-4 mt-0.5 text-destructive" aria-hidden />
            <div>
              <p className="font-medium text-destructive">Last attempt failed</p>
              <p className="text-foreground/80">{job.error_summary}</p>
            </div>
          </div>
        )}
        <p className="text-sm text-muted-foreground">
          {job.rows_total} row(s) confirmed. Click below to run reconciliation.
        </p>
        <Button onClick={handleFinalize} disabled={finalize.isPending}>
          {finalize.isPending ? "Submitting…" : "Run reconciliation"}
        </Button>
      </CardContent>
    </Card>
  )
}
