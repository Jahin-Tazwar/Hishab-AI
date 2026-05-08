import { useEffect, useState } from "react"
import { toast } from "sonner"

import { MatchStatusBadge } from "@/components/reconciliation/MatchStatusBadge"
import { Button } from "@/components/ui/button"
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { useOverrideLineItem } from "@/hooks/useReconciliations"
import { formatBDT } from "@/lib/formatBDT"
import type { CAOverride, ReconLineItemRow } from "@/types/reconciliation"

interface Props {
  item: ReconLineItemRow | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

const NONE = "__none__"

/**
 * Detail drawer (modal dialog for now — sheet primitive isn't installed)
 * showing both PR and SF rows side by side, plus a CA override + notes
 * form. Saving calls useOverrideLineItem which invalidates the line items
 * query so the table refreshes.
 */
export function LineItemDrawer({ item, open, onOpenChange }: Props) {
  const override = useOverrideLineItem()
  const [decision, setDecision] = useState<CAOverride | null>(null)
  const [notes, setNotes] = useState("")

  useEffect(() => {
    if (!item) return
    setDecision(item.ca_override)
    setNotes(item.ca_notes ?? "")
  }, [item])

  if (!item) return null

  async function handleSave() {
    if (!item) return
    try {
      await override.mutateAsync({
        lineItemId: item.id,
        reconciliationId: item.reconciliation_id,
        ca_override: decision,
        ca_notes: notes.trim() || null,
      })
      toast.success("Override saved")
      onOpenChange(false)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Save failed")
    }
  }

  const flags = item.discrepancy_flags ?? {}

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-3">
            <span className="font-mono">{item.pr_invoice_no ?? "—"}</span>
            <MatchStatusBadge status={item.match_status} />
          </DialogTitle>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-4">
          <Panel title="Purchase register">
            <Field label="Supplier" value={item.pr_supplier_name} />
            <Field label="BIN" value={item.pr_supplier_bin} mono />
            <Field label="Date" value={item.pr_invoice_date} />
            <Field label="Taxable" value={formatBDT(item.pr_taxable_amount_bdt)} />
            <Field label="VAT" value={formatBDT(item.pr_vat_amount_bdt)} />
          </Panel>
          <Panel title="Supplier export">
            <Field label="Invoice" value={item.sf_invoice_no} mono />
            <Field label="Date" value={item.sf_invoice_date} />
            <Field label="Taxable" value={formatBDT(item.sf_taxable_amount_bdt)} />
            <Field label="VAT" value={formatBDT(item.sf_vat_amount_bdt)} />
            <Field
              label="Match score"
              value={item.match_score != null ? Number(item.match_score).toFixed(2) : null}
            />
          </Panel>
        </div>

        {(flags.reason || flags.date_off_by_days != null || flags.amount_diff_pct != null) && (
          <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
            <p className="font-medium">Discrepancy</p>
            {flags.reason && <p>{flags.reason}</p>}
            {flags.date_off_by_days != null && (
              <p>Date off by {flags.date_off_by_days} day(s)</p>
            )}
            {flags.amount_diff_pct != null && (
              <p>Amount diff: {(flags.amount_diff_pct * 100).toFixed(2)}%</p>
            )}
          </div>
        )}

        <div className="space-y-3 border-t pt-3">
          <p className="text-sm font-medium text-slate-700">CA decision</p>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="override">Override</Label>
              <Select
                value={decision ?? NONE}
                onValueChange={(v) => setDecision(v === NONE ? null : (v as CAOverride))}
              >
                <SelectTrigger id="override">
                  <SelectValue placeholder="None" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>None</SelectItem>
                  <SelectItem value="approved">Approved</SelectItem>
                  <SelectItem value="disputed">Disputed</SelectItem>
                  <SelectItem value="ignore">Ignore</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ca_notes">Notes</Label>
            <Textarea
              id="ca_notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Optional notes for this decision…"
              rows={3}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={override.isPending}>
            {override.isPending ? "Saving…" : "Save decision"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2 rounded-md border bg-slate-50 p-3">
      <p className="text-xs uppercase tracking-wide text-slate-500">{title}</p>
      <div className="space-y-1.5 text-sm">{children}</div>
    </div>
  )
}

function Field({
  label, value, mono,
}: { label: string; value: string | null | undefined; mono?: boolean }) {
  return (
    <div className="grid grid-cols-3 gap-2">
      <span className="text-slate-500">{label}</span>
      <span className={`col-span-2 ${mono ? "font-mono" : ""}`}>{value || "—"}</span>
    </div>
  )
}
