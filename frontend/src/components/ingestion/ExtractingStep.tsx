import { CheckCircle2, Loader2, XCircle } from "lucide-react"

import { EngineBadge } from "@/components/ingestion/EngineBadge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import type { IngestionFileOut } from "@/types/ingestion"

interface Props {
  files: IngestionFileOut[]
  filesDone: number
  filesTotal: number
}

const ICONS: Record<IngestionFileOut["status"], typeof Loader2> = {
  queued: Loader2,
  extracting: Loader2,
  extracted: CheckCircle2,
  failed: XCircle,
  skipped: XCircle,
}

const COLORS: Record<IngestionFileOut["status"], string> = {
  queued: "text-muted-foreground",
  extracting: "text-primary",
  extracted: "text-green-600 dark:text-green-500",
  failed: "text-destructive",
  skipped: "text-muted-foreground",
}

export function ExtractingStep({ files, filesDone, filesTotal }: Props) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Extracting…</CardTitle>
        <p className="text-sm text-muted-foreground">
          {filesDone} of {filesTotal} files done. This usually takes 10-30s; AI-vision files take longer.
        </p>
      </CardHeader>
      <CardContent>
        <ul className="divide-y">
          {files.map((f) => {
            const Icon = ICONS[f.status]
            const isSpinner = f.status === "queued" || f.status === "extracting"
            return (
              <li key={f.id} className="flex items-center gap-3 py-3">
                <Icon
                  className={cn("size-5 shrink-0", COLORS[f.status], isSpinner && "animate-spin")}
                  aria-hidden
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm">{f.original_filename}</p>
                  <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                    <EngineBadge engine={f.engine} />
                    <span>{f.status}</span>
                    {f.error && <span className="text-destructive">— {f.error}</span>}
                  </div>
                </div>
                {f.status === "extracted" && (
                  <span className="text-xs text-muted-foreground">{f.rows_extracted} rows</span>
                )}
              </li>
            )
          })}
        </ul>
      </CardContent>
    </Card>
  )
}
