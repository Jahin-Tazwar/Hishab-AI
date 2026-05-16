import { FileSpreadsheet, FileText, Image as ImageIcon, Upload, X } from "lucide-react"
import { useRef, useState, type DragEvent } from "react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

interface Props {
  files: File[]
  onChange: (files: File[]) => void
  accept: string
  disabled?: boolean
  rejectedReasons?: Record<string, string>
  maxBytes?: number
}

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(2)} KB`
  return `${(n / 1024 / 1024).toFixed(2)} MB`
}

function iconFor(file: File) {
  if (file.type.startsWith("image/")) return ImageIcon
  if (file.type === "application/pdf") return FileText
  return FileSpreadsheet
}

export function MultiFileDropzone({
  files, onChange, accept, disabled, rejectedReasons = {}, maxBytes,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)

  function handleAdd(picked: FileList | File[]) {
    const next = [...files, ...Array.from(picked)]
    onChange(next)
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setDragOver(false)
    if (disabled) return
    handleAdd(e.dataTransfer.files)
  }

  return (
    <div className="space-y-3">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        className={cn(
          "rounded-lg border-2 border-dashed p-6 text-center transition-colors",
          dragOver ? "border-primary bg-accent" : "border-border",
          disabled && "opacity-60 pointer-events-none",
        )}
      >
        <Upload className="mx-auto size-8 text-muted-foreground" aria-hidden />
        <p className="mt-2 text-sm">
          Drag & drop files here, or
          <label htmlFor="ingestion-upload" className="ml-1 cursor-pointer text-primary underline">
            browse
            <input
              ref={inputRef}
              id="ingestion-upload"
              type="file"
              multiple
              accept={accept}
              className="sr-only"
              aria-label="Upload files"
              disabled={disabled}
              onChange={(e) => {
                if (e.target.files) handleAdd(e.target.files)
                if (inputRef.current) inputRef.current.value = ""
              }}
            />
          </label>
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          XLSX, PDF, JPG, PNG, HEIC{maxBytes ? ` · max ${fmtBytes(maxBytes)} per file` : ""}
        </p>
      </div>

      {files.length > 0 && (
        <ul className="divide-y rounded-lg border">
          {files.map((f, idx) => {
            const Icon = iconFor(f)
            const rejected = rejectedReasons[f.name]
            return (
              <li
                key={`${f.name}-${idx}`}
                className="flex items-center gap-3 p-3"
              >
                <Icon className="size-5 shrink-0 text-muted-foreground" aria-hidden />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm">{f.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {fmtBytes(f.size)}
                    {rejected && (
                      <span className="ml-2 text-destructive">· {rejected}</span>
                    )}
                  </p>
                </div>
                <Button
                  size="icon"
                  variant="ghost"
                  aria-label={`Remove ${f.name}`}
                  disabled={disabled}
                  onClick={() => onChange(files.filter((_, i) => i !== idx))}
                >
                  <X className="size-4" />
                </Button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
