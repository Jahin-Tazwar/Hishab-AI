import { useState } from "react"

import { ExtractingStep } from "@/components/ingestion/ExtractingStep"
import { FinalizeStep } from "@/components/ingestion/FinalizeStep"
import { ReviewStep } from "@/components/ingestion/ReviewStep"
import { Stepper, statusToStep } from "@/components/ingestion/Stepper"
import { Card, CardContent } from "@/components/ui/card"
import { useJob } from "@/hooks/useIngestion"

interface Props {
  jobId: string
  clientId: string
}

export function IngestionWizard({ jobId, clientId }: Props) {
  const { data, isLoading, isError, error } = useJob(jobId)
  const [forceFinalize, setForceFinalize] = useState(false)

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading job…</p>
  }
  if (isError || !data) {
    return (
      <Card>
        <CardContent className="pt-6 text-sm text-destructive">
          {(error as Error)?.message ?? "Failed to load job."}
        </CardContent>
      </Card>
    )
  }

  const { job, files } = data
  const step = statusToStep(job.status)

  return (
    <div className="space-y-6">
      <Stepper activeStep={step} />
      {(job.status === "pending" || job.status === "extracting") && (
        <ExtractingStep
          files={files}
          filesDone={job.files_done}
          filesTotal={job.files_total}
        />
      )}
      {job.status === "ready_for_review" && !forceFinalize && (
        <ReviewStep
          job={job}
          files={files}
          onFinalize={() => setForceFinalize(true)}
        />
      )}
      {(job.status === "confirmed"
        || job.status === "reconciling"
        || job.status === "completed"
        || job.status === "failed"
        || (job.status === "ready_for_review" && forceFinalize)) && (
        <FinalizeStep job={job} clientId={clientId} />
      )}
    </div>
  )
}
