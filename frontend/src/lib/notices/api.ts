import { api } from "@/lib/api"
import {
  appendixJsonSchema, noticeDraftSchema, noticeSchema,
  type AppendixJson, type Notice, type NoticeDraft,
} from "@/types/notices"

const BASE = "/api/v1/notices"

export interface UploadNoticeResponse { notice_id: string }
export async function uploadNotice(
  clientId: string, file: File,
): Promise<UploadNoticeResponse> {
  const fd = new FormData()
  fd.append("file", file)
  // The axios instance defaults Content-Type to application/json; for
  // multipart we MUST clear it so axios computes the boundary header from
  // the FormData payload. Without this, the body is sent labelled JSON and
  // FastAPI returns 422 "missing field `file`".
  const { data } = await api.post<UploadNoticeResponse>(
    `${BASE}/?client_id=${encodeURIComponent(clientId)}`,
    fd,
    { headers: { "Content-Type": undefined as unknown as string } },
  )
  return data
}

export async function listNotices(clientId: string): Promise<Notice[]> {
  const { data } = await api.get<unknown[]>(
    `${BASE}/?client_id=${encodeURIComponent(clientId)}`,
  )
  return data.map((row) => noticeSchema.parse(row))
}

export async function getNotice(noticeId: string): Promise<Notice> {
  const { data } = await api.get<unknown>(`${BASE}/${noticeId}`)
  return noticeSchema.parse(data)
}

export interface RelinkPayload {
  client_id: string
  period_start: string
  period_end: string
  reconciliation_id?: string | null
}
export async function relinkNotice(
  noticeId: string, payload: RelinkPayload,
): Promise<void> {
  await api.post(`${BASE}/${noticeId}/relink`, payload)
}

export async function generateDraft(noticeId: string): Promise<void> {
  await api.post(`${BASE}/${noticeId}/draft`, {})
}

export async function getDraft(noticeId: string): Promise<NoticeDraft> {
  const { data } = await api.get<unknown>(`${BASE}/${noticeId}/draft`)
  return noticeDraftSchema.parse(data)
}

export interface SaveDraftPayload {
  body_html: string
  appendix_json: AppendixJson
}
export async function saveDraft(
  noticeId: string, payload: SaveDraftPayload,
): Promise<void> {
  // Validate appendix shape before sending — early failure beats 422
  appendixJsonSchema.parse(payload.appendix_json)
  await api.put(`${BASE}/${noticeId}/draft`, payload)
}

export async function finalizeDraft(noticeId: string): Promise<void> {
  await api.post(`${BASE}/${noticeId}/draft/finalize`, {})
}

export async function reopenDraft(noticeId: string, reason: string): Promise<void> {
  await api.post(`${BASE}/${noticeId}/draft/reopen`, { reason })
}

export interface RevisionMeta {
  id: string
  revision_no: number
  edited_by: string
  edit_source: "llm_generated" | "user_edit" | "regenerated"
  edit_reason: string | null
  created_at: string
}
export async function listDraftRevisions(noticeId: string): Promise<RevisionMeta[]> {
  const { data } = await api.get<RevisionMeta[]>(`${BASE}/${noticeId}/draft/revisions`)
  return data
}

export function exportDraftUrl(
  noticeId: string, format: "docx" | "pdf",
): string {
  return `${BASE}/${noticeId}/draft/export?format=${format}`
}
