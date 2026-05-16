// frontend/src/components/ingestion/ReviewStep.tsx
import { useMemo, useState } from "react"
import { toast } from "sonner"

import { RowDrawer } from "@/components/ingestion/RowDrawer"
import { RowsTable } from "@/components/ingestion/RowsTable"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useBulkConfirm, useJobRows } from "@/hooks/useIngestion"
import type { ExtractedRowOut, IngestionFileOut, JobOut } from "@/types/ingestion"

type Filter = "needs_review" | "all"

interface Props {
  job: JobOut
  files: IngestionFileOut[]
  onFinalize: () => void
}

export function ReviewStep({ job, files, onFinalize }: Props) {
  const [filter, setFilter] = useState<Filter>("needs_review")
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [openRowId, setOpenRowId] = useState<string | null>(null)

  const { data, isLoading } = useJobRows(job.id, filter)
  const rows: ExtractedRowOut[] = data?.rows ?? []
  const filesById = useMemo(() => new Map(files.map((f) => [f.id, f])), [files])

  const bulkConfirm = useBulkConfirm(job.id)

  function toggleSelect(id: string) {
    setSelected((s) => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }
  function toggleSelectAll() {
    if (rows.every((r) => selected.has(r.id))) {
      setSelected(new Set())
    } else {
      setSelected(new Set(rows.map((r) => r.id)))
    }
  }

  async function handleBulkConfirm() {
    if (selected.size === 0) return
    try {
      const n = await bulkConfirm.mutateAsync(Array.from(selected))
      setSelected(new Set())
      toast.success(`Confirmed ${n} row${n === 1 ? "" : "s"}`)
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  const openRow = rows.find((r) => r.id === openRowId)
  const finalizeDisabled = job.rows_needs_review > 0
  const finalizeReason = finalizeDisabled
    ? `${job.rows_needs_review} row(s) still need review`
    : undefined

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <CardTitle>Review extracted rows</CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            <FilterChip active={filter === "needs_review"} onClick={() => setFilter("needs_review")}>
              Needs review ({job.rows_needs_review})
            </FilterChip>
            <FilterChip active={filter === "all"} onClick={() => setFilter("all")}>
              All ({job.rows_total})
            </FilterChip>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading rows…</p>
          ) : (
            <RowsTable
              rows={rows}
              selected={selected}
              onToggleSelect={toggleSelect}
              onToggleSelectAll={toggleSelectAll}
              onRowClick={(id) => setOpenRowId(id)}
            />
          )}
          <div className="flex flex-wrap items-center gap-2">
            <Button
              onClick={handleBulkConfirm}
              disabled={selected.size === 0 || bulkConfirm.isPending}
              variant="secondary"
            >
              {bulkConfirm.isPending ? "Confirming…" : `Confirm selected (${selected.size})`}
            </Button>
            <span className="flex-1" />
            <Button
              onClick={onFinalize}
              disabled={finalizeDisabled}
              title={finalizeReason}
            >
              Finalize → run reconciliation
            </Button>
          </div>
        </CardContent>
      </Card>

      <RowDrawer
        jobId={job.id}
        row={openRow}
        file={openRow ? filesById.get(openRow.file_id) : undefined}
        open={Boolean(openRowId)}
        onOpenChange={(o) => { if (!o) setOpenRowId(null) }}
      />
    </div>
  )
}

function FilterChip({ active, onClick, children }: {
  active: boolean; onClick: () => void; children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        active
          ? "rounded-full bg-primary text-primary-foreground px-3 py-1 text-xs"
          : "rounded-full border border-border text-foreground px-3 py-1 text-xs hover:bg-accent"
      }
      aria-pressed={active}
    >
      {children}
    </button>
  )
}
