import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  exportDraftUrl, finalizeDraft, generateDraft, getDraft, getNotice,
  listDraftRevisions, listNotices, relinkNotice, reopenDraft,
  saveDraft, uploadNotice,
  type RelinkPayload, type SaveDraftPayload,
} from "@/lib/notices/api"
import type { Notice, NoticeDraft } from "@/types/notices"

const TRANSIENT: Notice["status"][] = ["pending", "parsing", "drafting"]

export const noticeKeys = {
  all: ["notices"] as const,
  list: (clientId: string) => ["notices", "list", clientId] as const,
  detail: (id: string) => ["notices", "detail", id] as const,
  draft: (id: string) => ["notices", "draft", id] as const,
  revisions: (id: string) => ["notices", "revisions", id] as const,
}

export function useNoticeList(clientId: string | undefined) {
  return useQuery({
    queryKey: noticeKeys.list(clientId ?? ""),
    enabled: Boolean(clientId),
    queryFn: () => listNotices(clientId!),
  })
}

export function useNotice(noticeId: string | undefined) {
  return useQuery<Notice>({
    queryKey: noticeKeys.detail(noticeId ?? ""),
    enabled: Boolean(noticeId),
    queryFn: () => getNotice(noticeId!),
    // Poll while a phase is in progress so the UI shows status transitions
    // without manual refresh.
    refetchInterval: (q) => {
      const s = q.state.data?.status
      return s && TRANSIENT.includes(s) ? 2_000 : false
    },
  })
}

export function useNoticeDraft(noticeId: string | undefined) {
  return useQuery<NoticeDraft>({
    queryKey: noticeKeys.draft(noticeId ?? ""),
    enabled: Boolean(noticeId),
    queryFn: () => getDraft(noticeId!),
    retry: (_failureCount, err) => {
      // 404 = no draft yet; don't retry — UI shows "Draft reply" CTA
      const status = (err as { status?: number })?.status
      return status !== 404
    },
  })
}

export function useUploadNotice(clientId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => uploadNotice(clientId, file),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: noticeKeys.list(clientId) })
    },
  })
}

export function useRelinkNotice(noticeId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: RelinkPayload) => relinkNotice(noticeId, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: noticeKeys.detail(noticeId) })
    },
  })
}

export function useGenerateDraft(noticeId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => generateDraft(noticeId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: noticeKeys.detail(noticeId) })
      void qc.invalidateQueries({ queryKey: noticeKeys.draft(noticeId) })
    },
  })
}

export function useSaveDraft(noticeId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (p: SaveDraftPayload) => saveDraft(noticeId, p),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: noticeKeys.revisions(noticeId) })
    },
  })
}

export function useFinalizeDraft(noticeId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => finalizeDraft(noticeId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: noticeKeys.detail(noticeId) })
      void qc.invalidateQueries({ queryKey: noticeKeys.draft(noticeId) })
    },
  })
}

export function useReopenDraft(noticeId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (reason: string) => reopenDraft(noticeId, reason),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: noticeKeys.draft(noticeId) })
    },
  })
}

export function useDraftRevisions(noticeId: string | undefined) {
  return useQuery({
    queryKey: noticeKeys.revisions(noticeId ?? ""),
    enabled: Boolean(noticeId),
    queryFn: () => listDraftRevisions(noticeId!),
  })
}

export { exportDraftUrl }
