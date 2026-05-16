// frontend/src/components/ingestion/FinalizeStep.tsx
import { CheckCircle2, Loader2, XCircle } from "lucide-react"
import { useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useFinalize } from "@/hooks/useIngestion"
import type { JobOut } from "@/types/ingestion"

interface Props {
  job: JobOut
  clientId: string
}

export function FinalizeStep({ job, clientId }: Props) {
  const navigate = useNavigate()
  const finalize = useFinalize(job.id)

  // Auto-navigate when reconciliation completes
  useEffect(() => {
    if (job.status === "completed" && job.reconciliation_id) {
      toast.success("Reconciliation complete")
      navigate(`/clients/${clientId}/recon/${job.reconciliation_id}`, { replace: true })
    }
  }, [job.status, job.reconciliation_id, clientId, navigate])

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

  return (
    <Card>
      <CardHeader><CardTitle>Ready to finalize</CardTitle></CardHeader>
      <CardContent className="space-y-3">
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
