/**
 * TanStack Query hooks for the reconciliation domain.
 *
 * Read paths go directly to Supabase (RLS handles tenant isolation).
 * Write paths (create reconciliation, override line item) go through
 * the FastAPI backend so business logic + audit trails stay server-side.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import {
  overrideLineItem,
  type LineItemOverrideResponse,
} from "@/lib/reconciliation/api"
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
 * plus optional notes. Routes through FastAPI so the server can recompute
 * the headline aggregates honoring override semantics, then returns the
 * new aggregates so we can warm the detail cache without a refetch.
 *
 * Invalidates BOTH `lineItems` (so the table re-renders with the new
 * ca_override / bucket) AND `detail` (so the hero KPI card reflects the
 * shifted Safe / At-risk totals).
 */
export function useOverrideLineItem() {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: async (input: {
      lineItemId: string
      reconciliationId: string
      ca_override: CAOverride | null
      ca_notes: string | null
    }): Promise<LineItemOverrideResponse> => {
      return overrideLineItem({
        reconciliationId: input.reconciliationId,
        lineItemId: input.lineItemId,
        ca_override: input.ca_override,
        ca_notes: input.ca_notes,
      })
    },
    onSuccess: (result, vars) => {
      // Patch the detail cache in place with the recomputed aggregates so
      // the hero card updates instantly, without waiting for a refetch.
      qc.setQueryData<ReconciliationRow | null>(
        reconKeys.detail(vars.reconciliationId),
        (current) => current
          ? {
              ...current,
              total_invoices: result.aggregates.total_invoices,
              matched_exact: result.aggregates.matched_exact,
              matched_fuzzy: result.aggregates.matched_fuzzy,
              partial_match: result.aggregates.partial_match,
              no_match: result.aggregates.no_match,
              total_vat_claimed_bdt: result.aggregates.total_vat_claimed_bdt,
              safe_itc_bdt: result.aggregates.safe_itc_bdt,
              at_risk_itc_bdt: result.aggregates.at_risk_itc_bdt,
            }
          : current,
      )
      // Refetch line items so the row's ca_override / bucket badge is fresh.
      void qc.invalidateQueries({ queryKey: reconKeys.lineItems(vars.reconciliationId) })
      // Best-effort: also refetch the header in the background so any
      // server-side derived field (e.g. updated_at) doesn't drift.
      void qc.invalidateQueries({ queryKey: reconKeys.detail(vars.reconciliationId) })
    },
  })
}
