import { toast } from "sonner"

import { ExtractingStep } from "@/components/ingestion/ExtractingStep"
import { FinalizeStep } from "@/components/ingestion/FinalizeStep"
import { HalfHeader } from "@/components/ingestion/HalfHeader"
import { ReviewStep } from "@/components/ingestion/ReviewStep"
import { UploadStep } from "@/components/ingestion/UploadStep"
import { useFinalize } from "@/hooks/useIngestion"
import type { JobOut, IngestionFileOut } from "@/types/ingestion"

interface Props {
  clientId: string
  periodStart: string
  periodEnd: string
  sfJob?: JobOut
  files: IngestionFileOut[]
  /** PR job id to link the new SF job to. Required when sfJob is undefined. */
  linkedPrJobId?: string
  onJobCreated: (jobId: string) => void
}

export function SupplierHalf({
  clientId, periodStart, periodEnd, sfJob, files, linkedPrJobId, onJobCreated,
}: Props) {
  // Always declare hooks unconditionally (Rules of Hooks); pass empty string
  // when there's no SF job yet — the mutation isn't invoked in that branch.
  const finalize = useFinalize(sfJob?.id ?? "")

  if (!sfJob) {
    return (
      <div className="space-y-3">
        <HalfHeader half="supplier_export" subState="upload" />
        <UploadStep
          clientId={clientId}
          kind="supplier_export"
          periodStart={periodStart}
          periodEnd={periodEnd}
          linkedPrJobId={linkedPrJobId}
          onCreated={onJobCreated}
        />
      </div>
    )
  }

  // Empty PENDING SF job (sf-only sessions: start_session pre-created the
  // SF job with `reuse_pr_doc_id` set and 0 files). Render UploadStep that
  // appends to the existing job.
  if (sfJob.status === "pending" && sfJob.files_total === 0) {
    return (
      <div className="space-y-3">
        <HalfHeader half="supplier_export" subState="upload" />
        <UploadStep
          clientId={clientId}
          kind="supplier_export"
          periodStart={periodStart}
          periodEnd={periodEnd}
          existingJobId={sfJob.id}
          onCreated={onJobCreated}
        />
      </div>
    )
  }

  if (sfJob.status === "pending" || sfJob.status === "extracting") {
    return (
      <div className="space-y-3">
        <HalfHeader half="supplier_export" subState="extract" />
        <ExtractingStep
          files={files}
          filesDone={sfJob.files_done}
          filesTotal={sfJob.files_total}
        />
      </div>
    )
  }

  if (sfJob.status === "ready_for_review") {
    return (
      <div className="space-y-3">
        <HalfHeader half="supplier_export" subState="review" />
        <ReviewStep
          job={sfJob}
          files={files}
          onFinalize={async () => {
            // Calling finalize on the SF job runs the full handoff:
            // ready_for_review → confirmed → reconciling → completed (or failed).
            // The wizard re-polls and SupplierHalf re-renders into FinalizeStep
            // as the status changes.
            try {
              await finalize.mutateAsync()
            } catch (e) {
              toast.error((e as Error).message)
            }
          }}
          confirmCtaLabel="Run reconciliation"
        />
      </div>
    )
  }

  // confirmed | reconciling | completed | failed → FinalizeStep.
  return (
    <div className="space-y-3">
      <HalfHeader half="supplier_export" subState="review" />
      <FinalizeStep job={sfJob} clientId={clientId} />
    </div>
  )
}
