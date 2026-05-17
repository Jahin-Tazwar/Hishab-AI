import { toast } from "sonner"

import { ExtractingStep } from "@/components/ingestion/ExtractingStep"
import { HalfHeader } from "@/components/ingestion/HalfHeader"
import { ReviewStep } from "@/components/ingestion/ReviewStep"
import { UploadStep } from "@/components/ingestion/UploadStep"
import { useConfirmJobReview } from "@/hooks/useIngestion"
import type { JobOut, IngestionFileOut } from "@/types/ingestion"

interface Props {
  clientId: string
  periodStart: string
  periodEnd: string
  prJob?: JobOut
  files: IngestionFileOut[]
  /** Called when the PR confirm CTA fires (after confirm-review API succeeds). */
  onContinueToSupplier: () => void
  /** Called when no PR job exists yet and the user uploads files. */
  onJobCreated: (jobId: string) => void
}

export function PurchaseHalf({
  clientId, periodStart, periodEnd, prJob, files,
  onContinueToSupplier, onJobCreated,
}: Props) {
  // Always declare hooks unconditionally; pass empty string when no job yet.
  const confirmReview = useConfirmJobReview(prJob?.id ?? "")

  if (!prJob) {
    return (
      <div className="space-y-3">
        <HalfHeader half="purchase_register" subState="upload" />
        <UploadStep
          clientId={clientId}
          kind="purchase_register"
          periodStart={periodStart}
          periodEnd={periodEnd}
          onCreated={onJobCreated}
        />
      </div>
    )
  }

  // Empty PENDING job (start_session pre-created it; user hasn't uploaded
  // yet). Render UploadStep that appends files to the existing job rather
  // than the ExtractingStep — there's nothing to extract yet.
  if (prJob.status === "pending" && prJob.files_total === 0) {
    return (
      <div className="space-y-3">
        <HalfHeader half="purchase_register" subState="upload" />
        <UploadStep
          clientId={clientId}
          kind="purchase_register"
          periodStart={periodStart}
          periodEnd={periodEnd}
          existingJobId={prJob.id}
          onCreated={onJobCreated}
        />
      </div>
    )
  }

  if (prJob.status === "pending" || prJob.status === "extracting") {
    return (
      <div className="space-y-3">
        <HalfHeader half="purchase_register" subState="extract" />
        <ExtractingStep
          files={files}
          filesDone={prJob.files_done}
          filesTotal={prJob.files_total}
        />
      </div>
    )
  }

  // ready_for_review OR confirmed → show ReviewStep with "Continue to supplier export"
  return (
    <div className="space-y-3">
      <HalfHeader half="purchase_register" subState="review" />
      <ReviewStep
        job={prJob}
        files={files}
        onFinalize={async () => {
          // ready_for_review → call confirm-review API first. confirmed → just continue.
          if (prJob.status === "ready_for_review") {
            try {
              await confirmReview.mutateAsync()
            } catch (e) {
              toast.error((e as Error).message)
              return
            }
          }
          onContinueToSupplier()
        }}
        confirmCtaLabel="Continue to supplier export"
      />
    </div>
  )
}
