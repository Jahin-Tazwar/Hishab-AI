/**
 * Storage upload helper for the private 'recon-files' bucket.
 *
 * Path layout per migration 0011:
 *   {tenant_id}/{client_id}/{batch_id}/{filename}.xlsx
 *
 * Where batch_id is a client-side UUID grouping the two files of a
 * reconciliation run together. After upload we insert a documents row
 * for each file and pass the resulting document ids to
 * POST /api/v1/reconciliations.
 */
import { supabase } from "./supabase"

const BUCKET = "recon-files"

export type ReconDocType = "purchase_register" | "supplier_export"

export interface UploadedDocument {
  document_id: string
  storage_path: string
  filename: string
  size_bytes: number
}

interface UploadArgs {
  tenantId: string
  clientId: string
  batchId: string
  docType: ReconDocType
  file: File
}

/**
 * Upload a single XLSX to Storage and create the matching `documents` row.
 * Returns the new document id (referenced by reconciliation requests).
 *
 * Throws on Storage errors (RLS, network, quota) or DB insert failure.
 */
export async function uploadReconDocument({
  tenantId,
  clientId,
  batchId,
  docType,
  file,
}: UploadArgs): Promise<UploadedDocument> {
  const safeName = file.name.replace(/[^a-zA-Z0-9_.-]/g, "_")
  const storagePath = `${tenantId}/${clientId}/${batchId}/${docType}-${safeName}`

  const { error: upErr } = await supabase.storage
    .from(BUCKET)
    .upload(storagePath, file, {
      cacheControl: "0",
      upsert: false,
      contentType:
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    })
  if (upErr) throw upErr

  const { data: userData } = await supabase.auth.getUser()
  const userId = userData.user?.id
  if (!userId) throw new Error("Not authenticated")

  const { data, error: insErr } = await supabase
    .from("documents")
    .insert({
      tenant_id: tenantId,
      client_id: clientId,
      original_filename: file.name,
      storage_path: storagePath,
      file_size_bytes: file.size,
      mime_type: file.type ||
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      doc_type: docType,
      uploaded_by: userId,
    })
    .select("id")
    .single()
  if (insErr) throw insErr

  return {
    document_id: data.id,
    storage_path: storagePath,
    filename: file.name,
    size_bytes: file.size,
  }
}
