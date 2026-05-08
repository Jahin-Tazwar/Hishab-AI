import { useCallback, useRef, useState } from "react"

import { cn } from "@/lib/utils"

interface Props {
  label: string
  accept?: string
  file: File | null
  onChange: (file: File | null) => void
  disabled?: boolean
  helpText?: string
}

const DEFAULT_ACCEPT =
  ".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

export function FileDropzone({
  label,
  accept = DEFAULT_ACCEPT,
  file,
  onChange,
  disabled = false,
  helpText,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [hover, setHover] = useState(false)

  const pick = useCallback((f: File | null) => {
    if (disabled) return
    onChange(f)
  }, [disabled, onChange])

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setHover(false)
    if (disabled) return
    const f = e.dataTransfer.files?.[0] ?? null
    pick(f)
  }

  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium text-slate-700">{label}</label>
      <div
        onDragOver={(e) => {
          e.preventDefault()
          if (!disabled) setHover(true)
        }}
        onDragLeave={() => setHover(false)}
        onDrop={handleDrop}
        onClick={() => !disabled && inputRef.current?.click()}
        className={cn(
          "flex min-h-[110px] cursor-pointer flex-col items-center justify-center rounded-md border border-dashed p-4 text-center transition",
          hover ? "border-slate-900 bg-slate-50" : "border-slate-300",
          disabled && "cursor-not-allowed opacity-60",
        )}
      >
        {file ? (
          <div className="space-y-1">
            <p className="text-sm font-medium text-slate-900">{file.name}</p>
            <p className="text-xs text-slate-500">
              {(file.size / 1024).toFixed(1)} KB
            </p>
            <button
              type="button"
              className="text-xs text-slate-500 underline hover:text-slate-700"
              onClick={(e) => {
                e.stopPropagation()
                pick(null)
              }}
              disabled={disabled}
            >
              Remove
            </button>
          </div>
        ) : (
          <div className="space-y-1">
            <p className="text-sm text-slate-600">
              Drop an .xlsx file here, or <span className="underline">browse</span>
            </p>
            {helpText && <p className="text-xs text-slate-500">{helpText}</p>}
          </div>
        )}
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          className="hidden"
          onChange={(e) => pick(e.target.files?.[0] ?? null)}
        />
      </div>
    </div>
  )
}
