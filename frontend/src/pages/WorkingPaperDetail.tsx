/**
 * Working paper detail page.
 * Path: /clients/:id/working-papers/:wpId
 *
 * Loads a working paper, defensively validates `composed_json` against the
 * recipe-specific Zod schema, and renders the header + kind-specific editor.
 *
 * The recipe registry means future kinds (audit pack, VDS recon, annual
 * file) drop into this same shell — we just add a branch on `kind`.
 */
import { Link, useParams } from "react-router-dom"

import { AtRiskItcScheduleEditor } from "@/components/working-papers/AtRiskItcScheduleEditor"
import { WorkingPaperHeader } from "@/components/working-papers/WorkingPaperHeader"
import { Card, CardContent } from "@/components/ui/card"
import { PageLoading } from "@/components/ui/Loading"
import { useClient } from "@/hooks/useClients"
import { useWorkingPaper } from "@/hooks/useWorkingPapers"
import {
  atRiskItcSchedulePayloadSchema, type AtRiskItcSchedulePayload,
} from "@/types/workingPapers"

export function WorkingPaperDetail() {
  const { id: clientId, wpId } = useParams<{ id: string; wpId: string }>()
  const wp = useWorkingPaper(wpId)
  const client = useClient(clientId)

  if (wp.isLoading) {
    return <PageLoading label="Loading working paper…" />
  }

  if (wp.isError || !wp.data) {
    return (
      <div className="space-y-3 p-6">
        <p className="text-sm text-red-700">Working paper not found.</p>
        <Link to={`/clients/${clientId}`} className="text-sm underline">
          Back to client
        </Link>
      </div>
    )
  }

  const workingPaper = wp.data

  // Defensive parse of the composed payload by kind.
  let payload: AtRiskItcSchedulePayload | null = null
  let payloadError: string | null = null
  if (workingPaper.kind === "at_risk_itc_schedule") {
    const parsed = atRiskItcSchedulePayloadSchema.safeParse(
      workingPaper.composed_json,
    )
    if (parsed.success) {
      payload = parsed.data
    } else {
      payloadError = parsed.error.issues
        .map((i) => `${i.path.join(".") || "(root)"}: ${i.message}`)
        .join("; ")
      // eslint-disable-next-line no-console
      console.error("Invalid working paper payload", parsed.error)
    }
  } else {
    payloadError = `Unsupported working paper kind: ${workingPaper.kind}`
  }

  return (
    <div className="space-y-6">
      <div>
        <Link
          to={`/clients/${clientId}`}
          className="text-sm text-slate-500 hover:underline"
        >
          ← Back to {client.data?.name ?? "client"}
        </Link>
      </div>

      <WorkingPaperHeader
        workingPaper={workingPaper}
        clientName={client.data?.name}
      />

      {workingPaper.is_stale ? (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
          <span className="font-medium">Source reconciliation changed.</span>{" "}
          The headline figures no longer match the reconciliation this paper was
          composed from. Regenerate to refresh the schedule
          {workingPaper.status === "finalized"
            ? " (reopen it first)"
            : ""}
          .
        </div>
      ) : null}

      {payload ? (
        <AtRiskItcScheduleEditor workingPaper={workingPaper} payload={payload} />
      ) : (
        <Card>
          <CardContent className="py-6">
            <p className="text-sm font-medium text-red-700">
              Could not render this working paper.
            </p>
            <p className="mt-1 text-xs text-slate-600">
              {payloadError ?? "Unknown payload shape."}
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
