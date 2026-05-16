/* eslint-disable react-refresh/only-export-components */
import { Check } from "lucide-react"

import { cn } from "@/lib/utils"
import type { JobStatus } from "@/types/ingestion"

const STEPS = ["Upload", "Extract", "Review", "Finalize"] as const
export type StepIndex = 1 | 2 | 3 | 4

export function statusToStep(status: JobStatus): StepIndex {
  switch (status) {
    case "pending":          return 1
    case "extracting":       return 2
    case "ready_for_review": return 3
    case "confirmed":
    case "reconciling":
    case "completed":
    case "failed":
      return 4
  }
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
