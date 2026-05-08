// frontend/src/components/compliance/EventStatusSelect.tsx
import { useState } from "react"
import { toast } from "sonner"

import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { useUpdateEventStatus } from "@/hooks/useCompliance"
import {
  EVENT_STATUS_LABELS, SELECTABLE_STATUSES, type EventStatus,
} from "@/types/compliance"

interface Props {
  eventId: string
  /**
   * Effective status for display. When the row is derived-overdue
   * (pending + due_date<today), the parent may pass "overdue" — but
   * the dropdown itself only lets the user choose from
   * SELECTABLE_STATUSES (pending/filed/waived/na). Choosing one
   * clears the derived-overdue badge naturally.
   */
  current: EventStatus
  disabled?: boolean
}

export function EventStatusSelect({ eventId, current, disabled }: Props) {
  const update = useUpdateEventStatus()
  // For "overdue" (derived) we still let the underlying value be pending so
  // the select shows the actionable state.
  const initial: EventStatus = current === "overdue" ? "pending" : current
  const [value, setValue] = useState<EventStatus>(initial)

  async function handleChange(next: string) {
    const status = next as EventStatus
    setValue(status)
    try {
      await update.mutateAsync({ id: eventId, status })
      toast.success(`Marked ${EVENT_STATUS_LABELS[status].toLowerCase()}`)
    } catch (e) {
      // Revert on failure
      setValue(initial)
      toast.error(e instanceof Error ? e.message : "Update failed")
    }
  }

  return (
    <Select
      value={value}
      onValueChange={handleChange}
      disabled={disabled || update.isPending}
    >
      <SelectTrigger className="h-7 w-32 text-xs">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {SELECTABLE_STATUSES.map((s) => (
          <SelectItem key={s} value={s}>
            {EVENT_STATUS_LABELS[s]}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
