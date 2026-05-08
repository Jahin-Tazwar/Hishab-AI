/**
 * Shared loading indicators. Two pieces:
 *
 *  <Spinner />        — small inline spinner. Use in buttons, table rows,
 *                       widget card bodies.
 *  <PageLoading />    — full-page skeleton with centered spinner + label.
 *                       Use for top-level page loads.
 */
import { Loader2 } from "lucide-react"

interface SpinnerProps {
  className?: string
}

export function Spinner({ className }: SpinnerProps) {
  return (
    <Loader2
      className={`h-4 w-4 animate-spin text-slate-500 ${className ?? ""}`}
      aria-label="Loading"
    />
  )
}

interface PageLoadingProps {
  label?: string
}

export function PageLoading({ label = "Loading…" }: PageLoadingProps) {
  return (
    <div className="flex min-h-[40vh] flex-col items-center justify-center gap-2">
      <Loader2 className="h-6 w-6 animate-spin text-slate-500" aria-label="Loading" />
      <p className="text-sm text-slate-500">{label}</p>
    </div>
  )
}
