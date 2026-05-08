/**
 * TanStack Query hooks for the reconciliation domain.
 *
 * Read paths go directly to Supabase (RLS handles tenant isolation).
 * Write paths (create reconciliation, override line item) go through
 * the FastAPI backend so business logic + audit trails stay server-side.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import { supabase } from "@/lib/supabase"
import type {
  CAOverride,
  ReconciliationCreateInput,
  ReconciliationCreateResponse,
  ReconciliationRow,
  ReconLineItemRow,
} from "@/types/reconciliation"

export const reconKeys = {
  all: ["reconciliations"] as const,
  listByClient: (clientId: string) =>
    ["reconciliations", "list", "client", clientId] as const,
  detail: (id: string) => ["reconciliations", "detail", id] as const,
  lineItems: (id: string) => ["reconciliations", "line-items", id] as const,
}

/**
 * List reconciliations for one client, newest first.
 */
export function useClientReconciliations(clientId: string | undefined) {
  return useQuery({
    queryKey: reconKeys.listByClient(clientId ?? ""),
    enabled: Boolean(clientId),
    queryFn: async (): Promise<ReconciliationRow[]> => {
      if (!clientId) return []
      const { data, error } = await supabase
        .from("vat_reconciliations")
        .select("*")
        .eq("client_id", clientId)
        .order("started_at", { ascending: false })
      if (error) throw error
      return (data ?? []) as ReconciliationRow[]
    },
  })
}

/**
 * One reconciliation header row (aggregates).
 */
export function useReconciliation(id: string | undefined) {
  return useQuery({
    queryKey: reconKeys.detail(id ?? ""),
    enabled: Boolean(id),
    queryFn: async (): Promise<ReconciliationRow | null> => {
      if (!id) return null
      const { data, error } = await supabase
        .from("vat_reconciliations")
        .select("*")
        .eq("id", id)
        .maybeSingle()
      if (error) throw error
      return (data as ReconciliationRow | null) ?? null
    },
  })
}

/**
 * Per-invoice rows for a reconciliation. Sorted no_match → partial → fuzzy → exact
 * to surface the highest-attention items first, matching the XLSX export order.
 */
export function useReconLineItems(id: string | undefined) {
  return useQuery({
    queryKey: reconKeys.lineItems(id ?? ""),
    enabled: Boolean(id),
    queryFn: async (): Promise<ReconLineItemRow[]> => {
      if (!id) return []
      const { data, error } = await supabase
        .from("recon_line_items")
        .select("*")
        .eq("reconciliation_id", id)
      if (error) throw error
      const rows = (data ?? []) as ReconLineItemRow[]
      const severity: Record<string, number> = {
        no_match: 0, partial: 1, fuzzy: 2, exact: 3,
      }
      return [...rows].sort((a, b) => {
        const sev = (severity[a.match_status] ?? 4) - (severity[b.match_status] ?? 4)
        if (sev !== 0) return sev
        return (a.pr_invoice_date ?? "").localeCompare(b.pr_invoice_date ?? "")
      })
    },
  })
}

/**
 * Run a new reconciliation. Returns the new id; the caller navigates to the
 * report page after success.
 */
export function useCreateReconciliation() {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: async (
      input: ReconciliationCreateInput,
    ): Promise<ReconciliationCreateResponse> => {
      const { data } = await api.post<ReconciliationCreateResponse>(
        "/api/v1/reconciliations",
        input,
      )
      return data
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: reconKeys.listByClient(vars.client_id) })
    },
  })
}

/**
 * Override a single line item's CA decision (approved / disputed / ignore)
 * plus optional notes. Updates Supabase directly — RLS scopes by tenant.
 */
export function useOverrideLineItem() {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: async ({
      lineItemId,
      reconciliationId,
      ca_override,
      ca_notes,
    }: {
      lineItemId: string
      reconciliationId: string
      ca_override: CAOverride | null
      ca_notes: string | null
    }): Promise<ReconLineItemRow> => {
      const { data, error } = await supabase
        .from("recon_line_items")
        .update({ ca_override, ca_notes })
        .eq("id", lineItemId)
        .select()
        .single()
      if (error) throw error
      // ensure recon line items list refreshes
      void qc.invalidateQueries({ queryKey: reconKeys.lineItems(reconciliationId) })
      return data as ReconLineItemRow
    },
  })
}
