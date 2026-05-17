/**
 * Backend client for the reconciliation domain. Reads still go directly to
 * Supabase (RLS handles tenant scope and avoids round-tripping through the
 * API for read-heavy pages); writes that need recompute / audit go through
 * FastAPI.
 */
import { api } from "@/lib/api"
import type { AggregatesDTO, CAOverride } from "@/types/reconciliation"

export interface LineItemOverrideResponse {
  line_item_id: string
  ca_override: CAOverride | null
  ca_notes: string | null
  aggregates: AggregatesDTO
}

/**
 * Update a CA's override + notes on a single line item and receive the
 * recomputed headline aggregates in the same response. The caller is
 * expected to update its TanStack Query caches with the returned values
 * (or just invalidate the relevant keys) so the hero KPIs and the table
 * stay in sync without a second round-trip.
 */
export async function overrideLineItem(input: {
  reconciliationId: string
  lineItemId: string
  ca_override: CAOverride | null
  ca_notes: string | null
}): Promise<LineItemOverrideResponse> {
  const { data } = await api.post<LineItemOverrideResponse>(
    `/api/v1/reconciliations/${input.reconciliationId}/line-items/${input.lineItemId}/override`,
    {
      ca_override: input.ca_override,
      ca_notes: input.ca_notes,
    },
  )
  return data
}
