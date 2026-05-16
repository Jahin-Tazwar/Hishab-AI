import { StatusChip } from "@/components/ingestion/StatusChip"
import { WarningChip } from "@/components/ingestion/WarningChip"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import { formatBDT } from "@/lib/formatBDT"
import type { ExtractedRowOut } from "@/types/ingestion"

interface Props {
  rows: ExtractedRowOut[]
  selected: Set<string>
  onToggleSelect: (id: string) => void
  onToggleSelectAll: () => void
  onRowClick: (id: string) => void
}

export function RowsTable({
  rows, selected, onToggleSelect, onToggleSelectAll, onRowClick,
}: Props) {
  const allSelected = rows.length > 0 && rows.every((r) => selected.has(r.id))
  return (
    <div className="rounded-lg border overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-10">
              <Checkbox
                checked={allSelected}
                onCheckedChange={onToggleSelectAll}
                aria-label="Select all rows"
              />
            </TableHead>
            <TableHead>Invoice</TableHead>
            <TableHead>Date</TableHead>
            <TableHead className="text-right">Taxable</TableHead>
            <TableHead className="text-right">VAT</TableHead>
            <TableHead>BIN</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Warnings</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => {
            const bin = r.row_data.supplier_bin ?? r.row_data.buyer_bin ?? ""
            return (
              <TableRow
                key={r.id}
                className="cursor-pointer hover:bg-accent/50"
                onClick={(e) => {
                  if ((e.target as HTMLElement).closest("[data-row-checkbox]")) return
                  onRowClick(r.id)
                }}
              >
                <TableCell data-row-checkbox onClick={(e) => e.stopPropagation()}>
                  <Checkbox
                    checked={selected.has(r.id)}
                    onCheckedChange={() => onToggleSelect(r.id)}
                    aria-label={`Select row ${r.row_data.invoice_no}`}
                  />
                </TableCell>
                <TableCell className="font-medium">{r.row_data.invoice_no}</TableCell>
                <TableCell>{r.row_data.invoice_date}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatBDT(Number(r.row_data.taxable_amount_bdt))}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatBDT(Number(r.row_data.vat_amount_bdt))}
                </TableCell>
                <TableCell className="font-mono text-xs">{bin || "—"}</TableCell>
                <TableCell><StatusChip status={r.status} /></TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-1">
                    {r.field_warnings.map((w, i) => (
                      <WarningChip key={`${w.code}-${i}`} warning={w} />
                    ))}
                  </div>
                </TableCell>
              </TableRow>
            )
          })}
          {rows.length === 0 && (
            <TableRow>
              <TableCell colSpan={8} className="text-center text-muted-foreground py-8">
                No rows match this filter.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  )
}
