import { relinkNotice } from "@/lib/notices/api"

const SESSION_KEY = "hishabai:from_notice_pending"

/** Capture `?from_notice=...` from the URL into sessionStorage so we
 * remember it across the wizard's multi-step lifecycle. */
export function captureFromNoticeFromQuery(search: string): void {
  const sp = new URLSearchParams(search)
  const id = sp.get("from_notice")
  if (id) sessionStorage.setItem(SESSION_KEY, id)
}

export function popFromNoticeId(): string | null {
  const v = sessionStorage.getItem(SESSION_KEY)
  if (v) sessionStorage.removeItem(SESSION_KEY)
  return v
}

/** Called by the wizard's success handler once a reconciliation_id exists. */
export async function notifyNoticeOfReconciliation(args: {
  clientId: string
  periodStart: string
  periodEnd: string
  reconciliationId: string
}): Promise<string | null> {
  const noticeId = popFromNoticeId()
  if (!noticeId) return null
  await relinkNotice(noticeId, {
    client_id: args.clientId,
    period_start: args.periodStart,
    period_end: args.periodEnd,
    reconciliation_id: args.reconciliationId,
  })
  return noticeId
}
