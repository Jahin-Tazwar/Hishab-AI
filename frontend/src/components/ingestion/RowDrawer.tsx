// frontend/src/components/ingestion/RowDrawer.tsx
import { zodResolver } from "@hookform/resolvers/zod"
import { useEffect } from "react"
import { useForm } from "react-hook-form"
import { toast } from "sonner"

import { SourcePreview } from "@/components/ingestion/SourcePreview"
import { WarningChip } from "@/components/ingestion/WarningChip"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { useConfirmRow, useEditRow, useRejectRow } from "@/hooks/useIngestion"
import { ExtractedRowDataSchema, type ExtractedRowData, type ExtractedRowOut, type IngestionFileOut } from "@/types/ingestion"

interface Props {
  jobId: string
  row: ExtractedRowOut | undefined
  file: IngestionFileOut | undefined
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function RowDrawer({ jobId, row, file, open, onOpenChange }: Props) {
  const { register, handleSubmit, reset, formState: { errors, isDirty } } =
    useForm<ExtractedRowData>({ resolver: zodResolver(ExtractedRowDataSchema) })

  const editMut = useEditRow(jobId)
  const confirmMut = useConfirmRow(jobId)
  const rejectMut = useRejectRow(jobId)

  useEffect(() => {
    if (row) reset(row.row_data)
  }, [row, reset])

  if (!row) return null

  async function onSave(values: ExtractedRowData) {
    try {
      await editMut.mutateAsync({ rowId: row!.id, body: values })
      toast.success("Row updated")
      onOpenChange(false)
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  async function onConfirm() {
    try {
      await confirmMut.mutateAsync(row!.id)
      toast.success("Row confirmed")
      onOpenChange(false)
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  async function onReject() {
    try {
      await rejectMut.mutateAsync(row!.id)
      toast.success("Row rejected")
      onOpenChange(false)
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex flex-col">
        <SheetHeader>
          <SheetTitle>Row {row.row_data.invoice_no}</SheetTitle>
          <SheetDescription>
            {file?.original_filename}{row.source_page_no ? ` · page ${row.source_page_no}` : ""}
          </SheetDescription>
        </SheetHeader>

        {row.field_warnings.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {row.field_warnings.map((w, i) => (
              <WarningChip key={`${w.code}-${i}`} warning={w} />
            ))}
          </div>
        )}

        <form onSubmit={handleSubmit(onSave)} className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="space-y-3">
            {(["invoice_no", "invoice_date", "taxable_amount_bdt", "vat_amount_bdt", "supplier_bin", "supplier_name", "buyer_bin"] as const).map((field) => (
              <div key={field} className="space-y-1">
                <Label htmlFor={field}>{field.replace(/_/g, " ")}</Label>
                <Input id={field} {...register(field)} aria-invalid={Boolean(errors[field])} />
                {errors[field] && (
                  <p className="text-xs text-destructive">{errors[field]?.message as string}</p>
                )}
              </div>
            ))}
            <div className="flex flex-wrap items-center gap-2 pt-2">
              <Button type="submit" disabled={!isDirty || editMut.isPending}>
                {editMut.isPending ? "Saving…" : "Save changes"}
              </Button>
              <Button type="button" variant="secondary" onClick={onConfirm} disabled={confirmMut.isPending}>
                Confirm as-is
              </Button>
              <Button type="button" variant="destructive" onClick={onReject} disabled={rejectMut.isPending}>
                Reject
              </Button>
            </div>
          </div>

          <div className="min-h-[420px] lg:min-h-0">
            <SourcePreview jobId={jobId} file={file} pageNo={row.source_page_no} />
          </div>
        </form>
      </SheetContent>
    </Sheet>
  )
}
