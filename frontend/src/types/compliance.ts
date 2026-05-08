// frontend/src/types/compliance.ts

/**
 * compliance_events row shape mirrored from the Supabase schema
 * (see migrations/0002_tenant_tables.sql).
 *
 * Note: status enum includes "overdue" but Phase D never writes it —
 * we derive overdue in queries from (status='pending' AND due_date<today).
 */
export const EVENT_STATUSES = [
  "pending",
  "filed",
  "overdue",
  "waived",
  "na",
] as const
export type EventStatus = (typeof EVENT_STATUSES)[number]

export const EVENT_STATUS_LABELS: Record<EventStatus, string> = {
  pending: "Pending",
  filed: "Filed",
  overdue: "Overdue",
  waived: "Waived",
  na: "N/A",
}

/** Statuses a CA can pick from the inline select. Excludes "overdue" (derived). */
export const SELECTABLE_STATUSES: EventStatus[] = [
  "pending",
  "filed",
  "waived",
  "na",
]

export interface ComplianceEventRow {
  id: string
  tenant_id: string
  client_id: string
  obligation_type: string
  period_start: string   // YYYY-MM-DD
  period_end: string
  due_date: string
  status: EventStatus
  filed_date: string | null
  notes: string | null
  created_at: string
  updated_at: string
}

/** Row enriched with the joined client name (for cross-tenant Dashboard widgets). */
export interface ComplianceEventWithClient extends ComplianceEventRow {
  client_name: string
}

/** Aggregate row for the OverdueClientsWidget. */
export interface OverdueByClient {
  client_id: string
  client_name: string
  overdue_count: number
}
