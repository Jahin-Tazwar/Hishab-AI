// frontend/src/components/ingestion/SourcePreview.tsx
import { useEffect, useState } from "react"

import { api } from "@/lib/api"
import { filePreviewUrl } from "@/lib/ingestion/api"
import type { IngestionFileOut } from "@/types/ingestion"

interface Props {
  jobId: string
  file: IngestionFileOut | undefined
  pageNo: number | null | undefined
}

/**
 * Renders a preview of the source file. Fetches the streamed bytes through
 * axios so the Authorization header is attached, then makes an Object URL
 * for <img>/<embed> consumers.
 */
export function SourcePreview({ jobId, file, pageNo }: Props) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null)

  useEffect(() => {
    let revoked = false
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setObjectUrl(null)
    if (!file) return
    api.get(filePreviewUrl(jobId, file.id), { responseType: "blob" })
      .then((res) => {
        if (revoked) return
        const url = URL.createObjectURL(res.data as Blob)
        setObjectUrl(url)
      })
      .catch(() => {
        // Surface as empty preview; the drawer still works for editing.
      })
    return () => {
      revoked = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, file?.id])

  if (!file) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        No source file available for this row.
      </div>
    )
  }
  if (!objectUrl) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        Loading preview…
      </div>
    )
  }
  if (file.mime_type === "application/pdf") {
    return (
      <embed
        src={`${objectUrl}#page=${pageNo ?? 1}`}
        type="application/pdf"
        className="h-full w-full rounded border"
        aria-label={`Preview of ${file.original_filename}`}
      />
    )
  }
  if (file.mime_type.startsWith("image/")) {
    return (
      <img
        src={objectUrl}
        alt={`Preview of ${file.original_filename}`}
        className="h-full w-full rounded border object-contain"
      />
    )
  }
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
      <p>Spreadsheet preview not supported inline.</p>
      <a href={objectUrl} download={file.original_filename} className="text-primary underline">
        Download {file.original_filename}
      </a>
    </div>
  )
}
