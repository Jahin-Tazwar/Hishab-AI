/**
 * Working paper page header — title, status badge, action buttons
 * (regenerate / export / finalize / reopen).
 *
 * Mirrors the NoticeDraft header. Export buttons are anchor tags with
 * `download` and point at the backend stream endpoint.
 */
import { useState } from "react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button, buttonVariants } from "@/components/ui/button"
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  exportWorkingPaperUrl,
  useFinalizeWorkingPaper,
  useRegenerateWorkingPaper,
  useReopenWorkingPaper,
} from "@/hooks/useWorkingPapers"
import { ApiError } from "@/lib/api"
import type { WorkingPaper } from "@/types/workingPapers"

const KIND_TITLES: Record<string, string> = {
  at_risk_itc_schedule: "At-Risk ITC Schedule",
}

interface Props {
  workingPaper: WorkingPaper
  clientName?: string
}

export function WorkingPaperHeader({ workingPaper, clientName }: Props) {
  const isFinalized = workingPaper.status === "finalized"
  const regenerate = useRegenerateWorkingPaper(workingPaper.id)
  const finalize = useFinalizeWorkingPaper(workingPaper.id)
  const reopen = useReopenWorkingPaper(workingPaper.id)

  const [reopenOpen, setReopenOpen] = useState(false)
  const [reopenReason, setReopenReason] = useState("")
  const [regenOpen, setRegenOpen] = useState(false)

  const title = KIND_TITLES[workingPaper.kind] ?? workingPaper.kind
  const hasNotes = workingPaper.notes_html.trim().length > 0
  const period = workingPaper.period_start && workingPaper.period_end
    ? `${workingPaper.period_start} → ${workingPaper.period_end}`
    : null

  async function handleRegenerate() {
    try {
      await regenerate.mutateAsync()
      toast.success("Regenerated.")
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : (e as Error).message)
    } finally {
      setRegenOpen(false)
    }
  }

  async function handleFinalize() {
    try {
      await finalize.mutateAsync()
      toast.success("Working paper finalized.")
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : (e as Error).message)
    }
  }

  async function handleReopen() {
    const reason = reopenReason.trim()
    if (reason.length < 3) {
      toast.error("Please provide a reason (at least 3 characters).")
      return
    }
    try {
      await reopen.mutateAsync(reason)
      toast.success("Reopened for editing.")
      setReopenOpen(false)
      setReopenReason("")
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : (e as Error).message)
    }
  }

  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-semibold">{title}</h1>
          <StatusBadge status={workingPaper.status} />
        </div>
        <p className="mt-1 text-sm text-slate-600">
          {clientName ?? ""}
          {clientName && period ? " · " : ""}
          {period}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          disabled={regenerate.isPending || isFinalized}
          onClick={() => {
            if (hasNotes) setRegenOpen(true)
            else void handleRegenerate()
          }}
        >
          Regenerate
        </Button>
        <a
          href={exportWorkingPaperUrl(workingPaper.id, "docx")}
          download
          className={buttonVariants({ variant: "outline" })}
        >
          Export .docx
        </a>
        <a
          href={exportWorkingPaperUrl(workingPaper.id, "pdf")}
          download
          className={buttonVariants({ variant: "outline" })}
        >
          Export PDF
        </a>
        {isFinalized ? (
          <Button onClick={() => setReopenOpen(true)}>
            Reopen for editing
          </Button>
        ) : (
          <Button onClick={handleFinalize} disabled={finalize.isPending}>
            {finalize.isPending ? "Finalizing…" : "Mark finalized"}
          </Button>
        )}
      </div>

      <Dialog open={regenOpen} onOpenChange={setRegenOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Regenerate this schedule?</DialogTitle></DialogHeader>
          <p className="text-sm text-slate-600">
            You have CA commentary saved. Regenerating will refresh the
            schedule data from the reconciliation but keep your notes intact.
            Continue?
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRegenOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleRegenerate} disabled={regenerate.isPending}>
              {regenerate.isPending ? "Regenerating…" : "Regenerate"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={reopenOpen} onOpenChange={setReopenOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Reopen for editing</DialogTitle></DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="reopen-reason">Reason (visible in history)</Label>
            <Textarea
              id="reopen-reason"
              value={reopenReason}
              onChange={(e) => setReopenReason(e.target.value)}
              placeholder="e.g. Supplier provided missing Mushak-6.3"
              rows={3}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setReopenOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleReopen} disabled={reopen.isPending}>
              {reopen.isPending ? "Reopening…" : "Reopen"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function StatusBadge({ status }: { status: WorkingPaper["status"] }) {
  if (status === "finalized") {
    return <Badge variant="secondary">Finalized</Badge>
  }
  return <Badge variant="outline">Draft</Badge>
}
