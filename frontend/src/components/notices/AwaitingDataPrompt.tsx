import { useNavigate } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { Notice } from "@/types/notices"

interface Props {
  notice: Notice
  clientId: string
}

/**
 * The wedge mechanic: when a notice arrives for a period we haven't
 * reconciled yet, route the user into the existing combined-ingestion
 * wizard pre-filled with this notice's client + period. The wizard
 * itself will call `relinkNotice` when it finishes (see Task 7.5).
 */
export function AwaitingDataPrompt({ notice, clientId }: Props) {
  const navigate = useNavigate()

  function startIngestion() {
    const qs = new URLSearchParams({
      from_notice: notice.id,
      period_start: notice.period_start ?? "",
      period_end: notice.period_end ?? "",
    }).toString()
    navigate(`/clients/${clientId}/ingestion/new?${qs}`)
  }

  return (
    <Card className="border-amber-200 bg-amber-50">
      <CardHeader>
        <CardTitle className="text-amber-900">Reconciliation data needed</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-amber-900">
          To draft a reply grounded in your actual position, HishabAI needs to
          reconcile your purchase register for{" "}
          <strong>{notice.period_start} → {notice.period_end}</strong> first.
        </p>
        <p className="text-xs text-amber-800">
          You'll be taken to the ingestion wizard pre-filled with this client
          and period. When it finishes, your reply draft will be ready
          automatically.
        </p>
        <Button onClick={startIngestion}>Upload purchase register →</Button>
      </CardContent>
    </Card>
  )
}
