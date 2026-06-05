/**
 * TanStack Query hooks for working papers.
 *
 * Compose is synchronous on the backend (no worker), so we do NOT poll the
 * detail — when the POST returns, the row is fully composed. The detail
 * query simply suppresses retries on 404 so a bogus :wpId surfaces cleanly.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  composeWorkingPaper,
  exportWorkingPaperUrl,
  finalizeWorkingPaper,
  getWorkingPaper,
  listWorkingPaperRevisions,
  listWorkingPapers,
  regenerateWorkingPaper,
  reopenWorkingPaper,
  updateWorkingPaperNotes,
} from "@/lib/working-papers/api"
import type {
  WorkingPaper, WorkingPaperKind, WorkingPaperRevision,
} from "@/types/workingPapers"

export const workingPaperKeys = {
  all: ["workingPapers"] as const,
  list: (clientId: string, kind?: string) =>
    ["workingPapers", "list", clientId, kind ?? "all"] as const,
  detail: (id: string) => ["workingPapers", "detail", id] as const,
  revisions: (id: string) => ["workingPapers", "revisions", id] as const,
}

export function useWorkingPapersList(
  clientId: string | undefined, kind?: WorkingPaperKind,
) {
  return useQuery<WorkingPaper[]>({
    queryKey: workingPaperKeys.list(clientId ?? "", kind),
    enabled: Boolean(clientId),
    queryFn: () => listWorkingPapers(clientId!, kind),
  })
}

export function useWorkingPaper(wpId: string | undefined) {
  return useQuery<WorkingPaper>({
    queryKey: workingPaperKeys.detail(wpId ?? ""),
    enabled: Boolean(wpId),
    queryFn: () => getWorkingPaper(wpId!),
    retry: (_failureCount, err) => {
      // 404 = no such working paper; the UI shows a "not found" state.
      const status = (err as { status?: number })?.status
      return status !== 404
    },
  })
}

export function useComposeWorkingPaper(reconciliationId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (kind: WorkingPaperKind) =>
      composeWorkingPaper(kind, reconciliationId),
    onSuccess: () => {
      // Invalidate every list cache (we don't know the clientId here).
      void qc.invalidateQueries({ queryKey: workingPaperKeys.all })
    },
  })
}

export function useUpdateWorkingPaperNotes(wpId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (notesHtml: string) => updateWorkingPaperNotes(wpId, notesHtml),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: workingPaperKeys.revisions(wpId) })
    },
  })
}

export function useRegenerateWorkingPaper(wpId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => regenerateWorkingPaper(wpId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: workingPaperKeys.detail(wpId) })
      void qc.invalidateQueries({ queryKey: workingPaperKeys.revisions(wpId) })
    },
  })
}

export function useFinalizeWorkingPaper(wpId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => finalizeWorkingPaper(wpId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: workingPaperKeys.detail(wpId) })
    },
  })
}

export function useReopenWorkingPaper(wpId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (reason: string) => reopenWorkingPaper(wpId, reason),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: workingPaperKeys.detail(wpId) })
    },
  })
}

export function useWorkingPaperRevisions(wpId: string | undefined) {
  return useQuery<WorkingPaperRevision[]>({
    queryKey: workingPaperKeys.revisions(wpId ?? ""),
    enabled: Boolean(wpId),
    queryFn: () => listWorkingPaperRevisions(wpId!),
  })
}

export { exportWorkingPaperUrl }
