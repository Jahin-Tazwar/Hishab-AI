import { Input } from "@/components/ui/input"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import type { AppendixJson, AppendixRow } from "@/types/notices"

interface Props {
  value: AppendixJson
  onChange: (next: AppendixJson) => void
  disabled?: boolean
}

export function ComputationAppendixTable({ value, onChange, disabled }: Props) {
  function setRow(i: number, patch: Partial<AppendixRow>) {
    const rows = value.rows.map((r, idx) => idx === i ? { ...r, ...patch } : r)
    onChange({ ...value, rows })
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Item</TableHead>
          <TableHead>Amount (BDT)</TableHead>
          <TableHead>Note</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {value.rows.length === 0 ? (
          <TableRow>
            <TableCell colSpan={3} className="text-slate-500">(no rows)</TableCell>
          </TableRow>
        ) : value.rows.map((r, i) => (
          <TableRow key={i}>
            <TableCell>
              <Input
                value={r.label}
                disabled={disabled}
                onChange={(e) => setRow(i, { label: e.target.value })}
              />
            </TableCell>
            <TableCell>
              <Input
                value={r.value_bdt ?? ""}
                disabled={disabled}
                onChange={(e) => setRow(i, { value_bdt: e.target.value || null })}
              />
            </TableCell>
            <TableCell>
              <Input
                value={r.note ?? ""}
                disabled={disabled}
                onChange={(e) => setRow(i, { note: e.target.value || null })}
              />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
