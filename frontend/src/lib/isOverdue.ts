import type { EventStatus } from "@/types/compliance"

interface Eventish {
  status: EventStatus
  due_date: string
}

/**
 * Derived "overdue" check used by the UI. A row is overdue when status
 * is "pending" and the due_date is strictly before today.
 *
 * `today` is passed in (rather than computed) so callers can keep a
 * single reference date for a render — keeps "Are these all overdue?"
 * answers stable across the same view.
 */
export function isOverdue(event: Eventish, today: Date): boolean {
  if (event.status !== "pending") return false
  const t = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime()
  const due = new Date(event.due_date).getTime()
  return due < t
}
