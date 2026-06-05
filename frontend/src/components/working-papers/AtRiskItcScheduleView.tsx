/**
 * Read-only renderer for the at_risk_itc_schedule composed payload.
 *
 * Layout:
 *   - Client header (name + BIN + period)
 *   - Summary card (4 metrics)
 *   - Per-supplier collapsible cards with a lines table
 *     (Accordion is not in the shadcn install — we use stateful Cards.)
 */
import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import { formatBDT } from "@/lib/formatBDT"
import { cn } from "@/lib/utils"
import {
  RECOMMENDED_ACTION_LABELS, WP_MATCH_STATUS_LABELS,
  type AtRiskItcSchedulePayload, type AtRiskSupplierGroup,
  type RecommendedAction, type WpMatchStatus,
} from "@/types/workingPapers"

const MATCH_BADGE_VARIANT: Record<
  WpMatchStatus,
  "default" | "secondary" | "destructive" | "outline"
> = {
  exact: "secondary",
  fuzzy: "outline",
  partial: "outline",
  no_match: "destructive",
}

const ACTION_BADGE_VARIANT: Record<
  RecommendedAction,
  "default" | "secondary" | "destructive" | "outline"
> = {
  chase_supplier: "outline",
  reverse_claim: "destructive",
  partner_review: "outline",
  approved_by_ca: "secondary",
  no_action: "secondary",
}

interface Props {
  payload: AtRiskItcSchedulePayload
}

export function AtRiskItcScheduleView({ payload }: Props) {
  return (
    <div className="space-y-4">
      <ClientHeader payload={payload} />
      <SummaryCard payload={payload} />

      <div className="space-y-3">
        <h2 className="text-lg font-semibold text-slate-900">
          Suppliers flagged ({payload.supplier_groups.length})
        </h2>
        {payload.supplier_groups.length === 0 ? (
          <Card>
            <CardContent className="py-6 text-sm text-slate-500">
              No at-risk suppliers in this period.
            </CardContent>
          </Card>
        ) : (
          payload.supplier_groups.map((group, idx) => (
            <SupplierGroupCard
              key={`${group.supplier_bin ?? group.supplier_name ?? "unknown"}-${idx}`}
              group={group}
            />
          ))
        )}
      </div>
    </div>
  )
}

function ClientHeader({ payload }: { payload: AtRiskItcSchedulePayload }) {
  return (
    <div className="rounded-md border bg-white p-4">
      <p className="text-xs uppercase tracking-wide text-slate-500">
        Client
      </p>
      <p className="text-base font-semibold text-slate-900">
        {payload.client_name}
        {payload.client_bin ? (
          <span className="ml-2 font-mono text-sm text-slate-500">
            {payload.client_bin}
          </span>
        ) : null}
      </p>
      <p className="mt-1 text-sm text-slate-600">
        Period: {payload.period_start} → {payload.period_end}
      </p>
    </div>
  )
}

function SummaryCard({ payload }: { payload: AtRiskItcSchedulePayload }) {
  const s = payload.summary
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">ITC summary</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <Metric label="Total VAT claimed" value={formatBDT(s.total_vat_claimed_bdt)} />
          <Metric label="Safe ITC" value={formatBDT(s.safe_itc_bdt)} tone="ok" />
          <Metric label="At-risk ITC" value={formatBDT(s.at_risk_itc_bdt)} tone="warn" />
          <Metric
            label="Lines flagged"
            value={`${s.at_risk_line_count} / ${s.total_lines}`}
            sub={`${s.supplier_count_at_risk} suppliers`}
          />
        </div>
      </CardContent>
    </Card>
  )
}

function Metric({
  label, value, sub, tone,
}: { label: string; value: string; sub?: string; tone?: "ok" | "warn" }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className={cn(
        "mt-1 text-lg font-semibold",
        tone === "ok" && "text-emerald-700",
        tone === "warn" && "text-amber-700",
        !tone && "text-slate-900",
      )}>
        {value}
      </p>
      {sub ? <p className="text-xs text-slate-500">{sub}</p> : null}
    </div>
  )
}

function SupplierGroupCard({ group }: { group: AtRiskSupplierGroup }) {
  const [open, setOpen] = useState(true)
  const supplierLabel = group.supplier_name ?? "(unnamed supplier)"

  return (
    <Card>
      <CardHeader>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex w-full items-center justify-between gap-3 text-left"
        >
          <div>
            <CardTitle className="text-base">{supplierLabel}</CardTitle>
            {group.supplier_bin ? (
              <p className="font-mono text-xs text-slate-500">
                {group.supplier_bin}
              </p>
            ) : null}
          </div>
          <div className="flex items-center gap-4">
            <div className="text-right">
              <p className="text-xs text-slate-500">VAT at risk</p>
              <p className="text-sm font-semibold text-amber-700">
                {formatBDT(group.total_vat_at_risk_bdt)}
              </p>
            </div>
            <Badge variant="outline">
              {group.line_count} {group.line_count === 1 ? "line" : "lines"}
            </Badge>
            <span className="text-slate-400" aria-hidden>
              {open ? "▾" : "▸"}
            </span>
          </div>
        </button>
      </CardHeader>
      {open ? (
        <CardContent>
          {group.lines.length === 0 ? (
            <p className="text-sm text-slate-500">No lines.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Invoice</TableHead>
                  <TableHead>Date</TableHead>
                  <TableHead className="text-right">Taxable</TableHead>
                  <TableHead className="text-right">VAT</TableHead>
                  <TableHead>Match</TableHead>
                  <TableHead>Recommended</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {group.lines.map((line) => (
                  <TableRow key={line.line_id}>
                    <TableCell className="font-medium">
                      {line.invoice_no ?? "—"}
                    </TableCell>
                    <TableCell>{line.invoice_date ?? "—"}</TableCell>
                    <TableCell className="text-right font-mono">
                      {formatBDT(line.taxable_amount_bdt ?? null)}
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {formatBDT(line.vat_amount_bdt ?? null)}
                    </TableCell>
                    <TableCell>
                      <Badge variant={MATCH_BADGE_VARIANT[line.match_status]}>
                        {WP_MATCH_STATUS_LABELS[line.match_status]}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={ACTION_BADGE_VARIANT[line.recommended_action]}>
                        {RECOMMENDED_ACTION_LABELS[line.recommended_action]}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      ) : null}
    </Card>
  )
}
