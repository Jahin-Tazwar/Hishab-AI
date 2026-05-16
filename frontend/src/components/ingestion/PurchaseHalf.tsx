import { ExtractingStep } from "@/components/ingestion/ExtractingStep"
import { HalfHeader } from "@/components/ingestion/HalfHeader"
import { ReviewStep } from "@/components/ingestion/ReviewStep"
import { UploadStep } from "@/components/ingestion/UploadStep"
import type { JobOut, IngestionFileOut } from "@/types/ingestion"

interface Props {
  clientId: string
  periodStart: string
  periodEnd: string
  prJob?: JobOut
  files: IngestionFileOut[]
  /** Called when the PR confirm CTA fires. The wizard then flips to the SF half. */
  onContinueToSupplier: () => void
  /** Called when no PR job exists yet and the user uploads files. */
  onJobCreated: (jobId: string) => void
}

export function PurchaseHalf({
  clientId, periodStart, periodEnd, prJob, files,
  onContinueToSupplier, onJobCreated,
}: Props) {
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

  if (prJob.status === "ready_for_review") {
    return (
      <div className="space-y-3">
        <HalfHeader half="purchase_register" subState="review" />
        <ReviewStep
          job={prJob}
          files={files}
          onFinalize={onContinueToSupplier}
          confirmCtaLabel="Continue to supplier export"
        />
      </div>
    )
  }

  // confirmed (waiting for the user to click into SF half) — show a small "done" affordance.
  return (
    <div className="space-y-3">
      <HalfHeader half="purchase_register" subState="review" />
      <ReviewStep
        job={prJob}
        files={files}
        onFinalize={onContinueToSupplier}
        confirmCtaLabel="Continue to supplier export"
      />
    </div>
  )
}
