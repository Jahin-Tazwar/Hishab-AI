import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"

import { MultiFileDropzone } from "@/components/ingestion/MultiFileDropzone"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useCreateJob } from "@/hooks/useIngestion"
import { ApiError } from "@/lib/api"
import type { JobKind } from "@/types/ingestion"

const ACCEPT = ".xlsx,.pdf,.jpg,.jpeg,.png,.heic"
const MAX_BYTES = 25 * 1024 * 1024

interface Props {
  clientId: string
  kind: JobKind
  periodStart: string
  periodEnd: string
  /** When set, the new job is linked to this PR job (only on kind=supplier_export). */
  linkedPrJobId?: string
  /** When set, persisted on the job; handoff will reuse the existing canonical XLSX. */
  reuseSfDocId?: string
  /** Called with the new job id after a successful upload. */
  onCreated: (jobId: string) => void
}

export function UploadStep({
  clientId, kind, periodStart, periodEnd,
  linkedPrJobId, reuseSfDocId, onCreated,
}: Props) {
  const navigate = useNavigate()
  const createJob = useCreateJob()

  const [files, setFiles] = useState<File[]>([])
  const oversize = files.find((f) => f.size > MAX_BYTES)
  const canSubmit = files.length > 0 && !oversize

  async function handleSubmit() {
    if (!canSubmit) return
    try {
      const res = await createJob.mutateAsync({
        client_id: clientId,
        period_start: periodStart,
        period_end: periodEnd,
        kind,
        files,
        linked_pr_job_id: linkedPrJobId,
        reuse_sf_doc_id: reuseSfDocId,
      })
      const rejected = res.files.filter((f) => !f.accepted)
      if (rejected.length === res.files.length) {
        toast.error("All files were rejected.")
        return
      } else if (rejected.length > 0) {
        toast.warning(`${rejected.length} file(s) rejected; proceeding with the rest.`)
      } else {
        toast.success("Upload received. Extracting…")
      }
      onCreated(res.job_id)
      // The wizard reads the new job ID via the parent; navigate only when
      // the parent didn't already handle the URL.
      if (!linkedPrJobId) {
        navigate(`/clients/${clientId}/ingestion/${res.job_id}`)
      }
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e as Error).message
      toast.error(msg)
    }
  }

  const title = kind === "purchase_register"
    ? "Upload purchase register"
    : "Upload supplier-filed export"

  return (
    <Card>
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <MultiFileDropzone
          files={files}
          onChange={setFiles}
          accept={ACCEPT}
          disabled={createJob.isPending}
          maxBytes={MAX_BYTES}
          rejectedReasons={
            oversize ? { [oversize.name]: `exceeds ${MAX_BYTES / 1024 / 1024} MB` } : {}
          }
        />
        <div className="flex items-center gap-3">
          <Button onClick={handleSubmit} disabled={!canSubmit || createJob.isPending}>
            {createJob.isPending ? "Uploading…" : `Upload ${files.length || ""} file${files.length === 1 ? "" : "s"}`.trim()}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
