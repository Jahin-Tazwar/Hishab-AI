/**
 * Typed API client for the Working Papers endpoints.
 *
 * Endpoint surface (mounted at /api/v1/working-papers):
 *   POST   /                       compose
 *   GET    /                       list (filter by client_id, kind)
 *   GET    /{wp_id}                detail
 *   PUT    /{wp_id}/notes          update CA commentary
 *   POST   /{wp_id}/regenerate     re-run the recipe in-place
 *   GET    /{wp_id}/revisions      revision history
 *   POST   /{wp_id}/finalize       lock (status → finalized)
 *   POST   /{wp_id}/reopen         unlock with reason
 *   GET    /{wp_id}/export?format= docx | pdf  (file stream)
 *
 * All bodies are JSON — no Content-Type override needed.
 */
import { api } from "@/lib/api"
import {
  workingPaperRevisionSchema,
  workingPaperSchema,
  type WorkingPaper,
  type WorkingPaperKind,
  type WorkingPaperRevision,
} from "@/types/workingPapers"

const BASE = "/api/v1/working-papers"

export interface ComposeWorkingPaperResponse { working_paper_id: string }

export async function composeWorkingPaper(
  kind: WorkingPaperKind, reconciliationId: string,
): Promise<ComposeWorkingPaperResponse> {
  const { data } = await api.post<ComposeWorkingPaperResponse>(
    `${BASE}/`,
    { kind, reconciliation_id: reconciliationId },
  )
  return data
}

export async function listWorkingPapers(
  clientId?: string, kind?: WorkingPaperKind,
): Promise<WorkingPaper[]> {
  const params = new URLSearchParams()
  if (clientId) params.set("client_id", clientId)
  if (kind) params.set("kind", kind)
  const qs = params.toString()
  const { data } = await api.get<unknown[]>(
    qs ? `${BASE}/?${qs}` : `${BASE}/`,
  )
  return data.map((row) => workingPaperSchema.parse(row))
}

export async function getWorkingPaper(wpId: string): Promise<WorkingPaper> {
  const { data } = await api.get<unknown>(`${BASE}/${wpId}`)
  return workingPaperSchema.parse(data)
}

export async function updateWorkingPaperNotes(
  wpId: string, notesHtml: string,
): Promise<void> {
  await api.put(`${BASE}/${wpId}/notes`, { notes_html: notesHtml })
}

export async function regenerateWorkingPaper(wpId: string): Promise<void> {
  await api.post(`${BASE}/${wpId}/regenerate`, {})
}

export async function finalizeWorkingPaper(wpId: string): Promise<void> {
  await api.post(`${BASE}/${wpId}/finalize`, {})
}

export async function reopenWorkingPaper(
  wpId: string, reason: string,
): Promise<void> {
  await api.post(`${BASE}/${wpId}/reopen`, { reason })
}

export async function listWorkingPaperRevisions(
  wpId: string,
): Promise<WorkingPaperRevision[]> {
  const { data } = await api.get<unknown[]>(`${BASE}/${wpId}/revisions`)
  return data.map((row) => workingPaperRevisionSchema.parse(row))
}

export function exportWorkingPaperUrl(
  wpId: string, format: "docx" | "pdf",
): string {
  return `${BASE}/${wpId}/export?format=${format}`
}
