// frontend/src/hooks/useIngestion.ts
import {
  useMutation, useQuery, useQueryClient,
} from "@tanstack/react-query"

import {
  addJobFiles,
  bulkConfirmRows, confirmJobReview, confirmRow, createJob, editRow, finalizeJob,
  getJob, listRows, rejectRow, startSession,
  type CreateJobInput, type ListRowsParams,
} from "@/lib/ingestion/api"
import type { ExtractedRowData, JobStatus, SessionStartRequest } from "@/types/ingestion"

export const ingestionKeys = {
  all: ["ingestion"] as const,
  job: (id: string) => ["ingestion", "job", id] as const,
  rows: (id: string, filter: "needs_review" | "all") =>
    ["ingestion", "rows", id, filter] as const,
}

/** Terminal job statuses where polling stops. */
const TERMINAL: JobStatus[] = ["completed", "failed"]

/**
 * Fetches a job + its files. Polls every 2s while non-terminal so the
 * Extracting / Reconciling steps update without manual refresh.
 */
export function useJob(jobId: string | undefined) {
  return useQuery({
    queryKey: ingestionKeys.job(jobId ?? ""),
    enabled: Boolean(jobId),
    queryFn: () => getJob(jobId!),
    refetchInterval: (q) => {
      const status = q.state.data?.job.status
      if (!status || TERMINAL.includes(status)) return false
      if (status === "extracting" || status === "reconciling") return 2000
      return 5000
    },
  })
}

export function useJobRows(
  jobId: string | undefined, filter: "needs_review" | "all" = "needs_review",
  params: Omit<ListRowsParams, "filter"> = {},
) {
  return useQuery({
    queryKey: ingestionKeys.rows(jobId ?? "", filter),
    enabled: Boolean(jobId),
    queryFn: () => listRows(jobId!, { ...params, filter }),
  })
}

export function useCreateJob() {
  return useMutation({
    mutationFn: (input: CreateJobInput) => createJob(input),
  })
}

/** Adds files to an existing PENDING job. Invalidates the job query on success. */
export function useAddJobFiles(jobId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (files: File[]) => addJobFiles(jobId, files),
    onSuccess: () => qc.invalidateQueries({ queryKey: ingestionKeys.job(jobId) }),
  })
}

export function useEditRow(jobId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ rowId, body }: { rowId: string; body: ExtractedRowData }) =>
      editRow(jobId, rowId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ingestionKeys.job(jobId) })
      qc.invalidateQueries({ queryKey: ["ingestion", "rows", jobId] })
    },
  })
}

export function useConfirmRow(jobId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (rowId: string) => confirmRow(jobId, rowId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ingestionKeys.job(jobId) })
      qc.invalidateQueries({ queryKey: ["ingestion", "rows", jobId] })
    },
  })
}

export function useRejectRow(jobId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (rowId: string) => rejectRow(jobId, rowId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ingestionKeys.job(jobId) })
      qc.invalidateQueries({ queryKey: ["ingestion", "rows", jobId] })
    },
  })
}

export function useBulkConfirm(jobId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (rowIds: string[]) => bulkConfirmRows(jobId, rowIds),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ingestionKeys.job(jobId) })
      qc.invalidateQueries({ queryKey: ["ingestion", "rows", jobId] })
    },
  })
}

export function useFinalize(jobId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => finalizeJob(jobId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ingestionKeys.job(jobId) })
    },
  })
}

export function useStartSession() {
  return useMutation({
    mutationFn: (input: SessionStartRequest) => startSession(input),
  })
}

export function useConfirmJobReview(jobId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => confirmJobReview(jobId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ingestionKeys.job(jobId) }),
  })
}
