// Mock supabase before importing api — the axios request interceptor calls
// supabase.auth.getSession(); in jsdom this would hit real Supabase. We mock
// it here (minimal scope, preferred over a global setup stub) so the
// interceptor returns a null session and the request proceeds unauthenticated.
import { vi } from "vitest"

vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
    },
  },
}))

import MockAdapter from "axios-mock-adapter"
import { afterEach, beforeEach, describe, expect, it } from "vitest"

import { api } from "@/lib/api"
import {
  bulkConfirmRows,
  confirmRow,
  createJob,
  editRow,
  finalizeJob,
  getJob,
  listRows,
  rejectRow,
} from "@/lib/ingestion/api"

let mock: MockAdapter

beforeEach(() => { mock = new MockAdapter(api) })
afterEach(() => { mock.restore() })

const JOB_ID = "00000000-0000-0000-0000-000000000001"
const ROW_ID = "00000000-0000-0000-0000-000000000002"
const CLIENT_ID = "00000000-0000-0000-0000-000000000010"
const FILE_ID = "00000000-0000-0000-0000-000000000020"

describe("ingestion api client", () => {
  it("createJob posts multipart and parses response", async () => {
    mock.onPost("/api/v1/ingestion/jobs").reply(201, {
      job_id: JOB_ID,
      files: [{
        file_id: FILE_ID, original_filename: "x.xlsx",
        mime_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        byte_size: 100, accepted: true, rejection_reason: null,
      }],
    })
    const res = await createJob({
      client_id: CLIENT_ID,
      period_start: "2026-05-01", period_end: "2026-05-31",
      kind: "purchase_register",
      files: [new File(["x"], "x.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" })],
    })
    expect(res.job_id).toBe(JOB_ID)
  })

  it("getJob returns parsed JobDetailOut", async () => {
    mock.onGet(`/api/v1/ingestion/jobs/${JOB_ID}`).reply(200, {
      job: {
        id: JOB_ID, tenant_id: CLIENT_ID, client_id: CLIENT_ID,
        kind: "purchase_register", period_start: "2026-05-01", period_end: "2026-05-31",
        status: "ready_for_review",
        files_total: 1, files_done: 1, rows_total: 3, rows_needs_review: 0,
        error_summary: null, reconciliation_id: null,
        created_at: "2026-05-15T12:00:00+00:00",
        updated_at: "2026-05-15T12:00:00+00:00",
        completed_at: null,
      },
      files: [],
    })
    const res = await getJob(JOB_ID)
    expect(res.job.status).toBe("ready_for_review")
  })

  it("listRows handles pagination params", async () => {
    mock.onGet(`/api/v1/ingestion/jobs/${JOB_ID}/rows`, { params: { filter: "all", limit: 50, offset: 0 } })
      .reply(200, { rows: [], total: 0, has_more: false })
    const res = await listRows(JOB_ID, { filter: "all", limit: 50, offset: 0 })
    expect(res.total).toBe(0)
  })

  it("editRow PATCHes the new payload", async () => {
    mock.onPatch(`/api/v1/ingestion/jobs/${JOB_ID}/rows/${ROW_ID}`).reply(200, {
      id: ROW_ID, file_id: FILE_ID, job_id: JOB_ID, source_page_no: null,
      row_data: { invoice_no: "X", invoice_date: "2026-05-01", taxable_amount_bdt: "1.00", vat_amount_bdt: "0.15" },
      row_data_original: { invoice_no: "X", invoice_date: "2026-05-01", taxable_amount_bdt: "1.00", vat_amount_bdt: "0.15" },
      status: "edited", field_warnings: [],
      reviewed_by: null, reviewed_at: null,
      created_at: "2026-05-15T12:00:00+00:00",
    })
    const res = await editRow(JOB_ID, ROW_ID, {
      invoice_no: "X", invoice_date: "2026-05-01",
      taxable_amount_bdt: "1.00", vat_amount_bdt: "0.15",
    })
    expect(res.status).toBe("edited")
  })

  it("confirmRow POSTs and returns ok", async () => {
    mock.onPost(`/api/v1/ingestion/jobs/${JOB_ID}/rows/${ROW_ID}/confirm`).reply(200, { ok: true })
    await expect(confirmRow(JOB_ID, ROW_ID)).resolves.toBeUndefined()
  })

  it("rejectRow POSTs and returns ok", async () => {
    mock.onPost(`/api/v1/ingestion/jobs/${JOB_ID}/rows/${ROW_ID}/reject`).reply(200, { ok: true })
    await expect(rejectRow(JOB_ID, ROW_ID)).resolves.toBeUndefined()
  })

  it("bulkConfirmRows sends row_ids and returns count", async () => {
    mock.onPost(`/api/v1/ingestion/jobs/${JOB_ID}/rows/bulk-confirm`).reply(200, { confirmed_count: 3 })
    const n = await bulkConfirmRows(JOB_ID, [ROW_ID, ROW_ID, ROW_ID])
    expect(n).toBe(3)
  })

  it("finalizeJob returns reconciliation_id", async () => {
    mock.onPost(`/api/v1/ingestion/jobs/${JOB_ID}/finalize`).reply(200, {
      reconciliation_id: "00000000-0000-0000-0000-000000000099",
    })
    const res = await finalizeJob(JOB_ID)
    expect(res.reconciliation_id).toBe("00000000-0000-0000-0000-000000000099")
  })
})
