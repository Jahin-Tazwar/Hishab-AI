/**
 * Run a new reconciliation: upload PR + supplier-export XLSX, pick a
 * period, kick off the synchronous backend pipeline, navigate to the
 * report page on success.
 */
import { useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"
import { toast } from "sonner"

import { FileDropzone } from "@/components/reconciliation/FileDropzone"
import { PeriodPicker } from "@/components/reconciliation/PeriodPicker"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useClient } from "@/hooks/useClients"
import { useCreateReconciliation } from "@/hooks/useReconciliations"
import { useUserProfile } from "@/hooks/useUserProfile"
import { ApiError } from "@/lib/api"
import { uploadReconDocument } from "@/lib/reconStorage"
import { reconciliationCreateSchema } from "@/types/reconciliation"

function _newUuid(): string {
  // crypto.randomUUID is widely available in modern browsers + Vite preview
  return globalThis.crypto.randomUUID()
}

export function ReconNew() {
  const { id: clientId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: profile } = useUserProfile()
  const { data: client } = useClient(clientId)
  const create = useCreateReconciliation()

  const [prFile, setPrFile] = useState<File | null>(null)
  const [sfFile, setSfFile] = useState<File | null>(null)
  const [period, setPeriod] = useState({ start: "", end: "" })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const periodError =
    period.start && period.end && period.end < period.start
      ? "Period end must be on or after period start"
      : undefined

  const canSubmit =
    Boolean(prFile && sfFile && period.start && period.end && !periodError && clientId && profile)

  async function handleSubmit() {
    if (!canSubmit || !clientId || !profile || !prFile || !sfFile) return
    setSubmitting(true)
    setError(null)
    try {
      const batchId = _newUuid()

      // 1. Upload both files in parallel
      const [pr, sf] = await Promise.all([
        uploadReconDocument({
          tenantId: profile.tenant_id, clientId, batchId,
          docType: "purchase_register", file: prFile,
        }),
        uploadReconDocument({
          tenantId: profile.tenant_id, clientId, batchId,
          docType: "supplier_export", file: sfFile,
        }),
      ])

      // 2. Validate before sending
      const payload = reconciliationCreateSchema.parse({
        client_id: clientId,
        period_start: period.start,
        period_end: period.end,
        purchase_register_doc_id: pr.document_id,
        supplier_data_doc_id: sf.document_id,
      })

      // 3. Run the reconciliation
      const res = await create.mutateAsync(payload)
      toast.success("Reconciliation complete")
      navigate(`/clients/${clientId}/recon/${res.reconciliation_id}`)
    } catch (e) {
      const msg = e instanceof ApiError ? e.message
        : e instanceof Error ? e.message
        : "Reconciliation failed"
      setError(msg)
      toast.error(msg)
    } finally {
      setSubmitting(false)
    }
  }

  if (!clientId) {
    return <div className="p-8 text-slate-600">Missing client id.</div>
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <Link to={`/clients/${clientId}`} className="text-sm text-slate-500 hover:underline">
          ← Back to {client?.name ?? "client"}
        </Link>
        <h1 className="text-2xl font-bold text-slate-900 mt-1">New reconciliation</h1>
        <p className="text-slate-600 text-sm mt-1">
          Upload the purchase register and the NBR supplier-filed export for the same period.
          Matching runs synchronously and typically completes in seconds.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Files</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <FileDropzone
            label="Purchase register"
            file={prFile}
            onChange={setPrFile}
            disabled={submitting}
            helpText="Required columns: invoice_no, supplier_bin, supplier_name, invoice_date, taxable_amount_bdt, vat_amount_bdt"
          />
          <FileDropzone
            label="Supplier-filed export"
            file={sfFile}
            onChange={setSfFile}
            disabled={submitting}
            helpText="Required columns: invoice_no, invoice_date, taxable_amount_bdt, vat_amount_bdt, buyer_bin"
          />
          <p className="text-xs text-slate-500">
            Need a starter file? Download:{" "}
            <a className="underline" href="/templates/purchase-register-template.xlsx">
              purchase register
            </a>{" "}
            ·{" "}
            <a className="underline" href="/templates/supplier-export-template.xlsx">
              supplier export
            </a>
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Period</CardTitle>
        </CardHeader>
        <CardContent>
          <PeriodPicker
            start={period.start}
            end={period.end}
            onChange={setPeriod}
            disabled={submitting}
            errorMessage={periodError}
          />
        </CardContent>
      </Card>

      {error && (
        <p className="text-sm text-red-600">{error}</p>
      )}

      <div className="flex items-center gap-3">
        <Button onClick={handleSubmit} disabled={!canSubmit || submitting}>
          {submitting ? "Running…" : "Run reconciliation"}
        </Button>
        <Link
          to={`/clients/${clientId}`}
          className="text-sm text-slate-500 hover:underline"
        >
          Cancel
        </Link>
      </div>
    </div>
  )
}
