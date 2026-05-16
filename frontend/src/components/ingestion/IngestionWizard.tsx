import { useQueryClient } from "@tanstack/react-query"

import { PurchaseHalf } from "@/components/ingestion/PurchaseHalf"
import { Stepper, statusToStep } from "@/components/ingestion/Stepper"
import { SupplierHalf } from "@/components/ingestion/SupplierHalf"
import { Card, CardContent } from "@/components/ui/card"
import { ingestionKeys, useJob } from "@/hooks/useIngestion"

interface Props {
  /** The PR job id (or, in the SF-only / PR-reused case, the SF job id). */
  prJobId: string
  clientId: string
}

export function IngestionWizard({ prJobId, clientId }: Props) {
  const qc = useQueryClient()
  const primary = useJob(prJobId)

  // Derive the secondary job id BEFORE the loading guard so the useJob
  // hook call below is unconditional (Rules of Hooks).
  const primaryJob = primary.data?.job
  const isSfOnlySession =
    primaryJob?.kind === "supplier_export" && Boolean(primaryJob?.reuse_pr_doc_id)
  const secondaryJobId =
    (!isSfOnlySession && primaryJob?.linked_sf_job_id) || undefined
  const secondary = useJob(secondaryJobId)

  if (primary.isLoading) {
    return <p className="text-sm text-muted-foreground">Loading job…</p>
  }
  if (primary.isError || !primary.data) {
    return (
      <Card>
        <CardContent className="pt-6 text-sm text-destructive">
          {(primary.error as Error)?.message ?? "Failed to load job."}
        </CardContent>
      </Card>
    )
  }

  const primaryFiles = primary.data.files

  // SF-only path: the "primary" job IS the SF job. No PR job exists.
  if (isSfOnlySession) {
    const step = statusToStep(undefined, primary.data.job)
    return (
      <div className="space-y-6">
        <Stepper activeStep={step} />
        <SupplierHalf
          clientId={clientId}
          periodStart={primary.data.job.period_start}
          periodEnd={primary.data.job.period_end}
          sfJob={primary.data.job}
          files={primaryFiles}
          onJobCreated={() => { /* SF job already exists in this path */ }}
        />
      </div>
    )
  }

  // Standard path: PR job is primary. SF job (if any) was already fetched
  // via `secondary` above.
  const prJob = primary.data.job
  const sfJob = secondary.data?.job
  const sfFiles = secondary.data?.files ?? []

  const step = statusToStep(prJob, sfJob)

  function handleSfCreated(newSfJobId: string) {
    qc.invalidateQueries({ queryKey: ingestionKeys.job(prJob.id) })
    qc.invalidateQueries({ queryKey: ingestionKeys.job(newSfJobId) })
  }

  return (
    <div className="space-y-6">
      <Stepper activeStep={step} />

      {/* Half 1: Purchase register — shown while PR is not yet confirmed
          (waiting on user to advance via confirm-review). */}
      {(prJob.status !== "confirmed" && prJob.status !== "completed") && (
        <PurchaseHalf
          clientId={clientId}
          periodStart={prJob.period_start}
          periodEnd={prJob.period_end}
          prJob={prJob}
          files={primaryFiles}
          onContinueToSupplier={() => {
            qc.invalidateQueries({ queryKey: ingestionKeys.job(prJob.id) })
          }}
          onJobCreated={() => { /* PR job already exists in this branch */ }}
        />
      )}

      {/* Half 2: Supplier export — shown once PR is confirmed/completed. */}
      {(prJob.status === "confirmed" || prJob.status === "completed") && (
        <SupplierHalf
          clientId={clientId}
          periodStart={prJob.period_start}
          periodEnd={prJob.period_end}
          sfJob={sfJob}
          files={sfFiles}
          linkedPrJobId={prJob.id}
          onJobCreated={handleSfCreated}
        />
      )}
    </div>
  )
}
