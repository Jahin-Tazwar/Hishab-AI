import { describe, expect, it } from "vitest"
import { render, screen } from "@testing-library/react"

import { Stepper, statusToStep } from "@/components/ingestion/Stepper"
import type { JobOut } from "@/types/ingestion"

function pr(status: JobOut["status"], extras: Partial<JobOut> = {}): JobOut {
  return {
    id: "p", tenant_id: "t", client_id: "c", kind: "purchase_register",
    period_start: "2026-05-01", period_end: "2026-05-31",
    status, files_total: 0, files_done: 0,
    rows_total: 0, rows_needs_review: 0,
    error_summary: null, reconciliation_id: null,
    linked_pr_job_id: null, linked_sf_job_id: null,
    reuse_pr_doc_id: null, reuse_sf_doc_id: null,
    created_at: "2026-05-10T00:00:00+00:00",
    updated_at: "2026-05-10T00:00:00+00:00",
    completed_at: null,
    ...extras,
  } as JobOut
}

function sf(status: JobOut["status"], extras: Partial<JobOut> = {}): JobOut {
  return pr(status, { kind: "supplier_export", ...extras })
}

describe("statusToStep", () => {
  it("returns 1 (Setup) when neither half exists", () => {
    expect(statusToStep(undefined, undefined)).toBe(1)
  })

  it("returns 2 (Purchase register) for an active PR job before SF exists", () => {
    expect(statusToStep(pr("extracting"), undefined)).toBe(2)
  })

  it("returns 3 (Supplier export) once SF job exists", () => {
    expect(statusToStep(pr("confirmed"), sf("extracting"))).toBe(3)
  })

  it("returns 4 (Reconcile) for SF reconciling", () => {
    expect(statusToStep(pr("confirmed"), sf("reconciling"))).toBe(4)
  })

  it("returns 5 (Done) when SF is completed", () => {
    expect(statusToStep(pr("completed"), sf("completed"))).toBe(5)
  })

  it("PR with reuse_sf_doc_id and confirmed → step 4 (Reconcile pending)", () => {
    expect(statusToStep(pr("confirmed", { reuse_sf_doc_id: "doc" }), undefined)).toBe(4)
  })

  it("SF-only session (PR reused) extracting → step 3", () => {
    expect(statusToStep(undefined, sf("extracting", { reuse_pr_doc_id: "doc" }))).toBe(3)
  })
})

describe("<Stepper />", () => {
  it("renders 5 step labels", () => {
    render(<Stepper activeStep={1} />)
    expect(screen.getByText("Setup")).toBeInTheDocument()
    expect(screen.getByText("Purchase register")).toBeInTheDocument()
    expect(screen.getByText("Supplier export")).toBeInTheDocument()
    expect(screen.getByText("Reconcile")).toBeInTheDocument()
    expect(screen.getByText("Done")).toBeInTheDocument()
  })
})
