import { render, screen } from "@testing-library/react"
import { describe, it, expect } from "vitest"

import { AuditDefensePackView } from "@/components/working-papers/AuditDefensePackView"
import type { AuditDefensePackPayload } from "@/types/workingPapers"

const payload: AuditDefensePackPayload = {
  kind: "audit_defense_pack", recipe_version: "v1",
  client_id: "11111111-1111-1111-1111-111111111111",
  client_name: "Padma Textiles Ltd", client_bin: "001234567-0101",
  client_tin: "555000111",
  notice_id: "22222222-2222-2222-2222-222222222222",
  notice: { notice_no: "NBR/4471", notice_date: "2026-05-20",
    notice_type: "input_vat_mismatch", period_start: "2026-04-01",
    period_end: "2026-04-30", taxpayer_bin: "001234567-0101",
    taxpayer_tin: "555000111", alleged_itc_claimed_bdt: "2847500.00",
    alleged_itc_allowed_bdt: "2412000.00", alleged_shortfall_bdt: "435500.00" },
  reconciliation_id: null, reconciled_position: null,
  override_log: [{ supplier_name: "Meghna", supplier_bin: "0044",
    invoice_no: "MP-7798", ca_override: "disputed", ca_notes: "pending" }],
  drafted_reply: { language: "bn", status: "finalized",
    body_html: "<p>reply text</p>", citations: [{ source_ref: "Rule 21" }] },
  evidence_index: [{ ref: "E-01", document_id: null, filename: "notice.pdf",
    source_type: "nbr_notice", bucket: "notices", storage_path: "t/c/n.pdf" }],
}

describe("AuditDefensePackView", () => {
  it("renders the notice, override log, reply and evidence", () => {
    render(<AuditDefensePackView payload={payload} />)
    expect(screen.getByText(/NBR\/4471/)).toBeInTheDocument()
    expect(screen.getByText(/MP-7798/)).toBeInTheDocument()
    expect(screen.getByText(/reply text/)).toBeInTheDocument()
    expect(screen.getByText(/E-01/)).toBeInTheDocument()
    expect(screen.getByText(/notice.pdf/)).toBeInTheDocument()
  })

  it("shows an empty-state when no reconciliation is linked", () => {
    render(<AuditDefensePackView payload={payload} />)
    expect(screen.getByText(/No reconciliation linked/i)).toBeInTheDocument()
  })
})
