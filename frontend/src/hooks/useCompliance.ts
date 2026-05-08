// frontend/src/hooks/useCompliance.ts
/**
 * Compliance / calendar query hooks.
 *
 * All reads scoped automatically by RLS. Status writes go directly to
 * Supabase — the audit trigger captures the user via PostgREST's
 * automatic request.jwt.claim.sub setting.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { supabase } from "@/lib/supabase"
import type {
  ComplianceEventRow,
  ComplianceEventWithClient,
  EventStatus,
  OverdueByClient,
} from "@/types/compliance"
import type { ReconciliationRow } from "@/types/reconciliation"

export const complianceKeys = {
  all: ["compliance"] as const,
  upcoming: (days: number) => ["compliance", "upcoming", days] as const,
  byClient: (clientId: string, status: string) =>
    ["compliance", "by-client", clientId, status] as const,
  overdueByClient: () => ["compliance", "overdue-by-client"] as const,
  recentReconciliations: (limit: number) =>
    ["compliance", "recent-reconciliations", limit] as const,
}

function _todayISO(): string {
  return new Date().toISOString().slice(0, 10)
}

function _addDaysISO(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}

/** Events with due_date in [today, today+daysAhead], joined to client name. */
export function useUpcomingEvents(daysAhead = 30) {
  return useQuery({
    queryKey: complianceKeys.upcoming(daysAhead),
    queryFn: async (): Promise<ComplianceEventWithClient[]> => {
      const { data, error } = await supabase
        .from("compliance_events")
        .select("*, clients!inner(name)")
        .gte("due_date", _todayISO())
        .lte("due_date", _addDaysISO(daysAhead))
        .order("due_date", { ascending: true })
      if (error) throw error
      // Supabase returns the joined row as { ..., clients: { name } }
      return (data ?? []).map((row: ComplianceEventRow & { clients: { name: string } }) => {
        const { clients, ...rest } = row
        return { ...rest, client_name: clients.name }
      })
    },
  })
}

/** All events for one client; optional status filter; due-date ascending. */
export function useClientEvents(
  clientId: string | undefined,
  status: EventStatus | "all" = "all",
) {
  return useQuery({
    queryKey: complianceKeys.byClient(clientId ?? "", status),
    enabled: Boolean(clientId),
    queryFn: async (): Promise<ComplianceEventRow[]> => {
      if (!clientId) return []
      let q = supabase
        .from("compliance_events")
        .select("*")
        .eq("client_id", clientId)
        .order("due_date", { ascending: true })
      if (status !== "all" && status !== "overdue") {
        q = q.eq("status", status)
      } else if (status === "overdue") {
        q = q.eq("status", "pending").lt("due_date", _todayISO())
      }
      const { data, error } = await q
      if (error) throw error
      return (data ?? []) as ComplianceEventRow[]
    },
  })
}

/**
 * Counts of (status='pending' AND due_date<today) grouped by client.
 * Implementation: fetch the rows + reduce on the client. Volume is small
 * (one row per overdue obligation per client), and this avoids
 * RLS-edge-case issues with PostgREST aggregates.
 */
export function useOverdueByClient() {
  return useQuery({
    queryKey: complianceKeys.overdueByClient(),
    queryFn: async (): Promise<OverdueByClient[]> => {
      const { data, error } = await supabase
        .from("compliance_events")
        .select("client_id, clients!inner(name)")
        .eq("status", "pending")
        .lt("due_date", _todayISO())
      if (error) throw error
      const byClient = new Map<string, OverdueByClient>()
      for (const row of data ?? []) {
        // PostgREST + Supabase JS may type the inner-join `clients` as an
        // array of one or as a single object depending on the relation
        // metadata. Cast through unknown — we know it's a single row here
        // because clients!inner(...) is a non-null FK.
        const r = row as unknown as { client_id: string; clients: { name: string } }
        const existing = byClient.get(r.client_id)
        if (existing) {
          existing.overdue_count += 1
        } else {
          byClient.set(r.client_id, {
            client_id: r.client_id,
            client_name: r.clients.name,
            overdue_count: 1,
          })
        }
      }
      return [...byClient.values()].sort(
        (a, b) => b.overdue_count - a.overdue_count,
      )
    },
  })
}

/** Most-recent reconciliations across the tenant (joined to client name). */
export function useRecentReconciliations(limit = 5) {
  return useQuery({
    queryKey: complianceKeys.recentReconciliations(limit),
    queryFn: async (): Promise<(ReconciliationRow & { client_name: string })[]> => {
      const { data, error } = await supabase
        .from("vat_reconciliations")
        .select("*, clients!inner(name)")
        .order("started_at", { ascending: false })
        .limit(limit)
      if (error) throw error
      return (data ?? []).map((row: ReconciliationRow & { clients: { name: string } }) => {
        const { clients, ...rest } = row
        return { ...rest, client_name: clients.name }
      })
    },
  })
}

/**
 * Update a single event's status.
 *  - status='filed' → filed_date = today
 *  - any other status → filed_date = null
 *
 * Invalidates all compliance keys; the small over-fetch keeps the UI
 * trivially correct after status changes that affect multiple widgets.
 */
export function useUpdateEventStatus() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      id,
      status,
      notes,
    }: {
      id: string
      status: EventStatus
      notes?: string | null
    }): Promise<ComplianceEventRow> => {
      const update: Partial<ComplianceEventRow> = {
        status,
        filed_date: status === "filed" ? _todayISO() : null,
      }
      if (notes !== undefined) update.notes = notes
      const { data, error } = await supabase
        .from("compliance_events")
        .update(update)
        .eq("id", id)
        .select()
        .single()
      if (error) throw error
      return data as ComplianceEventRow
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: complianceKeys.all })
    },
  })
}
