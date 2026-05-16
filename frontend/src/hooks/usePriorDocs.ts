import { useQuery } from "@tanstack/react-query"

import { fetchRecentDocs } from "@/lib/ingestion/api"

export const priorDocsKeys = {
  forPeriod: (clientId: string, start: string, end: string) =>
    ["ingestion", "documents", "recent", clientId, start, end] as const,
}

/**
 * Looks up the most recent PR + SF documents for (client, period). Drives
 * the "Reuse prior PR/SF" checkboxes on the SetupStep.
 *
 * Disabled until all three params are non-empty (the period inputs start blank).
 */
export function usePriorDocs(clientId: string | undefined, periodStart: string, periodEnd: string) {
  const enabled = Boolean(clientId && periodStart && periodEnd)
  return useQuery({
    queryKey: priorDocsKeys.forPeriod(clientId ?? "", periodStart, periodEnd),
    enabled,
    queryFn: () => fetchRecentDocs({
      client_id: clientId!, period_start: periodStart, period_end: periodEnd,
    }),
    staleTime: 30_000,
  })
}
