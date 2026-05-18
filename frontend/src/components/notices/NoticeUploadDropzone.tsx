import { Upload } from "lucide-react"
import { useRef, useState, type DragEvent } from "react"

import { cn } from "@/lib/utils"

const ACCEPT = ".pdf,.jpg,.jpeg,.png,.heic,.webp"
const MAX_BYTES = 25 * 1024 * 1024

interface Props {
  disabled?: boolean
  onPicked: (file: File) => void
}

export function NoticeUploadDropzone({ disabled, onPicked }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function pick(file: File) {
    if (file.size > MAX_BYTES) {
      setError(`File too large (${(file.size / 1024 / 1024).toFixed(1)} MB > 25 MB)`)
      return
    }
    setError(null)
    onPicked(file)
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setDragOver(false)
    if (disabled) return
    const f = e.dataTransfer.files?.[0]
    if (f) pick(f)
  }

  return (
    <div className="space-y-2">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        className={cn(
          "rounded-lg border-2 border-dashed p-8 text-center transition-colors",
          dragOver ? "border-primary bg-accent" : "border-border",
          disabled && "opacity-60 pointer-events-none",
        )}
      >
        <Upload className="mx-auto size-8 text-muted-foreground" aria-hidden />
        <p className="mt-2 text-sm">
          Drop an NBR notice PDF or photo here, or
          <label htmlFor="notice-upload" className="ml-1 cursor-pointer text-primary underline">
            browse
            <input
              ref={inputRef}
              id="notice-upload"
              type="file"
              accept={ACCEPT}
              className="sr-only"
              aria-label="Upload notice"
              disabled={disabled}
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) pick(f)
                if (inputRef.current) inputRef.current.value = ""
              }}
            />
          </label>
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          PDF, JPG, PNG, HEIC, WEBP &middot; max 25 MB
        </p>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}
