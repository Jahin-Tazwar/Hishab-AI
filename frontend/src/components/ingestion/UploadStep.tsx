import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"

import { MultiFileDropzone } from "@/components/ingestion/MultiFileDropzone"
import { Stepper } from "@/components/ingestion/Stepper"
import { PeriodPicker } from "@/components/reconciliation/PeriodPicker"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { useCreateJob } from "@/hooks/useIngestion"
import { ApiError } from "@/lib/api"
import type { JobKind } from "@/types/ingestion"

const ACCEPT = ".xlsx,.pdf,.jpg,.jpeg,.png,.heic"
const MAX_BYTES = 25 * 1024 * 1024

interface Props {
  clientId: string
}

export function UploadStep({ clientId }: Props) {
  const navigate = useNavigate()
  const createJob = useCreateJob()

  const [files, setFiles] = useState<File[]>([])
  const [period, setPeriod] = useState({ start: "", end: "" })
  const [kind, setKind] = useState<JobKind>("purchase_register")

  const periodError = period.start && period.end && period.end < period.start
    ? "Period end must be on or after period start" : undefined
  const oversize = files.find((f) => f.size > MAX_BYTES)
  const canSubmit = files.length > 0 && !!period.start && !!period.end && !periodError && !oversize

  async function handleSubmit() {
    if (!canSubmit) return
    try {
      const res = await createJob.mutateAsync({
        client_id: clientId,
        period_start: period.start,
        period_end: period.end,
        kind,
        files,
      })
      const rejected = res.files.filter((f) => !f.accepted)
      if (rejected.length === res.files.length) {
        toast.error("All files were rejected.")
      } else if (rejected.length > 0) {
        toast.warning(`${rejected.length} file(s) rejected; proceeding with the rest.`)
      } else {
        toast.success("Upload received. Extracting…")
      }
      navigate(`/clients/${clientId}/ingestion/${res.job_id}`)
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e as Error).message
      toast.error(msg)
    }
  }

  return (
    <div className="space-y-6">
      <Stepper activeStep={1} />

      <Card>
        <CardHeader><CardTitle>Files</CardTitle></CardHeader>
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
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Document type &amp; period</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <fieldset>
            <legend className="text-sm font-medium mb-2">Document type</legend>
            <div role="radiogroup" className="flex gap-4">
              {(["purchase_register", "supplier_export"] as const).map((k) => (
                <label key={k} className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="kind"
                    value={k}
                    checked={kind === k}
                    onChange={() => setKind(k)}
                    disabled={createJob.isPending}
                  />
                  <span className="text-sm">
                    {k === "purchase_register" ? "Purchase register" : "Supplier-filed export"}
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          <div>
            <Label className="mb-2 block text-sm">Period</Label>
            <PeriodPicker
              start={period.start}
              end={period.end}
              onChange={setPeriod}
              disabled={createJob.isPending}
              errorMessage={periodError}
            />
          </div>
        </CardContent>
      </Card>

      <div className="flex items-center gap-3">
        <Button onClick={handleSubmit} disabled={!canSubmit || createJob.isPending}>
          {createJob.isPending ? "Uploading…" : `Upload ${files.length || ""} file${files.length === 1 ? "" : "s"}`.trim()}
        </Button>
      </div>
    </div>
  )
}
