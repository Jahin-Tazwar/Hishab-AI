import { ExtractingStep } from "@/components/ingestion/ExtractingStep"
import { FinalizeStep } from "@/components/ingestion/FinalizeStep"
import { HalfHeader } from "@/components/ingestion/HalfHeader"
import { ReviewStep } from "@/components/ingestion/ReviewStep"
import { UploadStep } from "@/components/ingestion/UploadStep"
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
          onFinalize={() => { /* FinalizeStep takes over via wizard step-routing */ }}
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
