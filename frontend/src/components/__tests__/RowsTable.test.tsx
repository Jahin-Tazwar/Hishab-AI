import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { RowsTable } from "@/components/ingestion/RowsTable"
import type { ExtractedRowOut } from "@/types/ingestion"

const baseRow = (overrides: Partial<ExtractedRowOut> = {}): ExtractedRowOut => ({
  id: "11111111-1111-1111-1111-111111111111",
  file_id: "22222222-2222-2222-2222-222222222222",
  job_id: "33333333-3333-3333-3333-333333333333",
  source_page_no: 1,
  row_data: {
    invoice_no: "INV-1", invoice_date: "2026-05-15",
    taxable_amount_bdt: "1000.00", vat_amount_bdt: "150.00",
    supplier_bin: "100200300", supplier_name: "ACME",
  },
  row_data_original: {
    invoice_no: "INV-1", invoice_date: "2026-05-15",
    taxable_amount_bdt: "1000.00", vat_amount_bdt: "150.00",
    supplier_bin: "100200300", supplier_name: "ACME",
  },
  status: "needs_review",
  field_warnings: [],
  reviewed_by: null, reviewed_at: null,
  created_at: "2026-05-15T12:00:00+00:00",
  ...overrides,
})

describe("RowsTable", () => {
  it("renders rows with status chips", () => {
    render(
      <RowsTable
        rows={[baseRow({ id: "a", status: "needs_review" }), baseRow({ id: "b", status: "auto_passed" })]}
        selected={new Set()}
        onToggleSelect={vi.fn()}
        onToggleSelectAll={vi.fn()}
        onRowClick={vi.fn()}
      />,
    )
    expect(screen.getByText("Needs review")).toBeInTheDocument()
    expect(screen.getByText("Auto")).toBeInTheDocument()
  })

  it("invokes onRowClick when a row is clicked", async () => {
    const user = userEvent.setup()
    const onRowClick = vi.fn()
    render(
      <RowsTable
        rows={[baseRow({ id: "abc" })]}
        selected={new Set()}
        onToggleSelect={vi.fn()}
        onToggleSelectAll={vi.fn()}
        onRowClick={onRowClick}
      />,
    )
    await user.click(screen.getByText("INV-1"))
    expect(onRowClick).toHaveBeenCalledWith("abc")
  })

  it("toggles select-all when header checkbox clicked", async () => {
    const user = userEvent.setup()
    const onToggleSelectAll = vi.fn()
    render(
      <RowsTable
        rows={[baseRow()]}
        selected={new Set()}
        onToggleSelect={vi.fn()}
        onToggleSelectAll={onToggleSelectAll}
        onRowClick={vi.fn()}
      />,
    )
    await user.click(screen.getByLabelText(/select all rows/i))
    expect(onToggleSelectAll).toHaveBeenCalled()
  })
})
