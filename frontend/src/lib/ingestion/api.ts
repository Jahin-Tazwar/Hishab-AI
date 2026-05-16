// frontend/src/lib/ingestion/api.ts
import { api } from "@/lib/api"
import {
  CreateJobResponseSchema,
  ExtractedRowDataSchema,
  ExtractedRowOutSchema,
  FinalizeResponseSchema,
  JobDetailOutSchema,
  JobKindEnum,
  RecentDocsOutSchema,
  RowsListOutSchema,
  SessionStartRequestSchema,
  SessionStartResponseSchema,
  type CreateJobResponse,
  type ExtractedRowData,
  type ExtractedRowOut,
  type FinalizeResponse,
  type JobDetailOut,
  type JobKind,
  type RecentDocsOut,
  type RowsListOut,
  type SessionStartRequest,
  type SessionStartResponse,
} from "@/types/ingestion"

export interface CreateJobInput {
  client_id: string
  period_start: string
  period_end: string
  kind: JobKind
  files: File[]
  linked_pr_job_id?: string
  reuse_pr_doc_id?: string
  reuse_sf_doc_id?: string
}

export async function createJob(input: CreateJobInput): Promise<CreateJobResponse> {
  const fd = new FormData()
  fd.append("client_id", input.client_id)
  fd.append("period_start", input.period_start)
  fd.append("period_end", input.period_end)
  fd.append("kind", JobKindEnum.parse(input.kind))
  if (input.linked_pr_job_id) fd.append("linked_pr_job_id", input.linked_pr_job_id)
  if (input.reuse_pr_doc_id)  fd.append("reuse_pr_doc_id",  input.reuse_pr_doc_id)
  if (input.reuse_sf_doc_id)  fd.append("reuse_sf_doc_id",  input.reuse_sf_doc_id)
  for (const f of input.files) fd.append("files", f, f.name)
  const { data } = await api.post("/api/v1/ingestion/jobs", fd, {
    headers: { "Content-Type": "multipart/form-data" },
  })
  return CreateJobResponseSchema.parse(data)
}

export async function getJob(jobId: string): Promise<JobDetailOut> {
  const { data } = await api.get(`/api/v1/ingestion/jobs/${jobId}`)
  return JobDetailOutSchema.parse(data)
}

export interface ListRowsParams {
  filter?: "needs_review" | "all"
  limit?: number
  offset?: number
}

export async function listRows(
  jobId: string, params: ListRowsParams = {},
): Promise<RowsListOut> {
  const { data } = await api.get(`/api/v1/ingestion/jobs/${jobId}/rows`, {
    params: {
      filter: params.filter ?? "needs_review",
      limit: params.limit ?? 200,
      offset: params.offset ?? 0,
    },
  })
  return RowsListOutSchema.parse(data)
}

export async function editRow(
  jobId: string, rowId: string, body: ExtractedRowData,
): Promise<ExtractedRowOut> {
  const validated = ExtractedRowDataSchema.parse(body)
  const { data } = await api.patch(
    `/api/v1/ingestion/jobs/${jobId}/rows/${rowId}`,
    validated,
  )
  return ExtractedRowOutSchema.parse(data)
}

export async function confirmRow(jobId: string, rowId: string): Promise<void> {
  await api.post(`/api/v1/ingestion/jobs/${jobId}/rows/${rowId}/confirm`)
}

export async function rejectRow(jobId: string, rowId: string): Promise<void> {
  await api.post(`/api/v1/ingestion/jobs/${jobId}/rows/${rowId}/reject`)
}

export async function bulkConfirmRows(
  jobId: string, rowIds: string[],
): Promise<number> {
  const { data } = await api.post(
    `/api/v1/ingestion/jobs/${jobId}/rows/bulk-confirm`,
    { row_ids: rowIds },
  )
  return data.confirmed_count as number
}

export async function finalizeJob(jobId: string): Promise<FinalizeResponse> {
  const { data } = await api.post(`/api/v1/ingestion/jobs/${jobId}/finalize`)
  return FinalizeResponseSchema.parse(data)
}

export async function confirmJobReview(jobId: string): Promise<void> {
  await api.post(`/api/v1/ingestion/jobs/${jobId}/confirm-review`)
}

export async function startSession(input: SessionStartRequest): Promise<SessionStartResponse> {
  const validated = SessionStartRequestSchema.parse(input)
  const { data } = await api.post("/api/v1/ingestion/sessions/start", validated)
  return SessionStartResponseSchema.parse(data)
}

export async function fetchRecentDocs(params: {
  client_id: string; period_start: string; period_end: string;
}): Promise<RecentDocsOut> {
  const { data } = await api.get("/api/v1/ingestion/documents/recent", { params })
  return RecentDocsOutSchema.parse(data)
}

/** Returns the URL where the original file is streamed. */
export function filePreviewUrl(jobId: string, fileId: string): string {
  return `${api.defaults.baseURL ?? ""}/api/v1/ingestion/jobs/${jobId}/files/${fileId}/preview`
}
