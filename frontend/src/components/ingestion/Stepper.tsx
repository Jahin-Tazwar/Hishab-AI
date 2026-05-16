/* eslint-disable react-refresh/only-export-components */
import { Check } from "lucide-react"

import { cn } from "@/lib/utils"
import type { JobOut } from "@/types/ingestion"

const STEPS = ["Setup", "Purchase register", "Supplier export", "Reconcile", "Done"] as const
export type StepIndex = 1 | 2 | 3 | 4 | 5

/**
 * Derive the active wizard step from the combined PR + SF job state.
 *
 *   undefined + undefined            → 1  Setup
 *   active PR + no SF                → 2  Purchase register
 *   PR confirmed + active SF         → 3  Supplier export
 *   SF reconciling                   → 4  Reconcile
 *   PR confirmed with reuse_sf       → 4  Reconcile (no SF job created)
 *   SF completed (terminal)          → 5  Done
 */
export function statusToStep(
  prJob: JobOut | undefined,
  sfJob: JobOut | undefined,
): StepIndex {
  if (!prJob && !sfJob) return 1

  // SF-only session (PR reused at session start, no PR job exists).
  if (!prJob && sfJob) {
    if (sfJob.status === "completed") return 5
    if (sfJob.status === "reconciling") return 4
    if (sfJob.status === "confirmed") return 4
    return 3 // pending | extracting | ready_for_review | failed
  }

  const pr = prJob!
  const prIsTerminal = pr.status === "confirmed" || pr.status === "completed"

  // Combined-completion: both halves done.
  if (pr.status === "completed" && (!sfJob || sfJob.status === "completed")) return 5

  if (!prIsTerminal) return 2

  // PR is confirmed/completed. If PR was created with reuse_sf_doc_id and SF
  // job was therefore never spawned, finalize runs from the PR job itself.
  if (!sfJob) {
    if (pr.reuse_sf_doc_id) {
      return 4
    }
    return 3 // PR confirmed, awaiting SF upload
  }

  // SF job exists.
  if (sfJob.status === "reconciling") return 4
  if (sfJob.status === "completed") return 5
  if (sfJob.status === "confirmed") return 4
  return 3
}

interface Props {
  activeStep: StepIndex
}

export function Stepper({ activeStep }: Props) {
  return (
    <ol className="flex w-full items-center" aria-label="Ingestion progress">
      {STEPS.map((label, idx) => {
        const step = (idx + 1) as StepIndex
        const done = step < activeStep
        const active = step === activeStep
        const isLast = idx === STEPS.length - 1
        return (
          <li
            key={label}
            aria-current={active ? "step" : undefined}
            className={cn("flex items-center", !isLast && "flex-1")}
          >
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  "flex size-7 items-center justify-center rounded-full border text-xs font-medium",
                  done && "bg-primary text-primary-foreground border-primary",
                  active && "border-primary text-primary",
                  !done && !active && "border-border text-muted-foreground",
                )}
              >
                {done ? <Check className="size-4" aria-hidden /> : step}
              </span>
              <span
                className={cn(
                  "text-sm",
                  active ? "text-foreground font-medium" : "text-muted-foreground",
                )}
              >
                {label}
              </span>
            </div>
            {!isLast && (
              <div
                className={cn(
                  "mx-3 h-px flex-1",
                  done ? "bg-primary" : "bg-border",
                )}
                aria-hidden
              />
            )}
          </li>
        )
      })}
    </ol>
  )
}
