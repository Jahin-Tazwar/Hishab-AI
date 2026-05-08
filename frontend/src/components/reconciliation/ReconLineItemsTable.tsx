import { useMemo, useState } from "react"

import { MatchStatusBadge } from "@/components/reconciliation/MatchStatusBadge"
import { Input } from "@/components/ui/input"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import { formatBDT } from "@/lib/formatBDT"
import { MATCH_STATUSES, type MatchStatus, type ReconLineItemRow } from "@/types/reconciliation"

interface Props {
  items: ReconLineItemRow[]
  onSelect: (item: ReconLineItemRow) => void
}

const STATUS_FILTERS: ("all" | MatchStatus)[] = ["all", ...MATCH_STATUSES]
const STATUS_LABELS: Record<typeof STATUS_FILTERS[number], string> = {
  all: "All",
  exact: "Exact",
  fuzzy: "Fuzzy",
  partial: "Partial",
  no_match: "No match",
}

export function ReconLineItemsTable({ items, onSelect }: Props) {
  const [search, setSearch] = useState("")
  const [filter, setFilter] = useState<typeof STATUS_FILTERS[number]>("all")

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return items.filter((it) => {
      if (filter !== "all" && it.match_status !== filter) return false
      if (!q) return true
      return (
        (it.pr_invoice_no ?? "").toLowerCase().includes(q) ||
        (it.pr_supplier_name ?? "").toLowerCase().includes(q) ||
        (it.pr_supplier_bin ?? "").toLowerCase().includes(q)
      )
    })
  }, [items, search, filter])

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <Input
          placeholder="Search invoice no / supplier / BIN…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-sm"
        />
        <div className="flex gap-1">
          {STATUS_FILTERS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setFilter(s)}
              className={`rounded-md border px-2.5 py-1 text-xs ${
                filter === s
                  ? "border-slate-900 bg-slate-900 text-white"
                  : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
              }`}
            >
              {STATUS_LABELS[s]}
            </button>
          ))}
        </div>
        <span className="ml-auto text-xs text-slate-500">
          {filtered.length} of {items.length} rows
        </span>
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Invoice</TableHead>
              <TableHead>Supplier</TableHead>
              <TableHead>BIN</TableHead>
              <TableHead>Date</TableHead>
              <TableHead className="text-right">VAT (BDT)</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>CA</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="text-center text-slate-500 py-6">
                  No matching rows.
                </TableCell>
              </TableRow>
            ) : (
              filtered.map((it) => (
                <TableRow
                  key={it.id}
                  onClick={() => onSelect(it)}
                  className="cursor-pointer hover:bg-slate-50"
                >
                  <TableCell className="font-mono">{it.pr_invoice_no ?? "—"}</TableCell>
                  <TableCell>{it.pr_supplier_name ?? "—"}</TableCell>
                  <TableCell className="font-mono">{it.pr_supplier_bin ?? "—"}</TableCell>
                  <TableCell>{it.pr_invoice_date ?? "—"}</TableCell>
                  <TableCell className="text-right font-mono">
                    {formatBDT(it.pr_vat_amount_bdt, { symbol: false })}
                  </TableCell>
                  <TableCell>
                    <MatchStatusBadge status={it.match_status} />
                  </TableCell>
                  <TableCell className="text-xs text-slate-600">
                    {it.ca_override ?? ""}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
