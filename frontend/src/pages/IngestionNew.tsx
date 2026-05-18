import { useEffect } from "react"
import { useLocation, useParams } from "react-router-dom"

import { SetupStep } from "@/components/ingestion/SetupStep"
import { Stepper } from "@/components/ingestion/Stepper"
import { PageHeader } from "@/components/layout/PageHeader"
import { useClient } from "@/hooks/useClients"
import { captureFromNoticeFromQuery } from "@/lib/notices/wizardCallback"

export function IngestionNew() {
  const { id: clientId } = useParams<{ id: string }>()
  const { data: client } = useClient(clientId)
  const location = useLocation()
  useEffect(() => {
    captureFromNoticeFromQuery(location.search)
  }, [location.search])
  if (!clientId) return <p className="text-muted-foreground">Missing client id.</p>
  return (
    <div className="max-w-3xl space-y-6">
      <PageHeader
        breadcrumbs={[
          { label: "Clients", to: "/clients" },
          { label: client?.name ?? "Client", to: `/clients/${clientId}` },
          { label: "New ingestion" },
        ]}
        title="New ingestion"
        subtitle="Pick a period. We'll walk you through the purchase register and the supplier-filed export, then reconcile."
      />
      <Stepper activeStep={1} />
      <SetupStep clientId={clientId} />
    </div>
  )
}
