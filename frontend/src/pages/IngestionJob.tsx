import { useParams } from "react-router-dom"

import { IngestionWizard } from "@/components/ingestion/IngestionWizard"
import { PageHeader } from "@/components/layout/PageHeader"
import { useClient } from "@/hooks/useClients"

export function IngestionJob() {
  const { id: clientId, jobId } = useParams<{ id: string; jobId: string }>()
  const { data: client } = useClient(clientId)
  if (!clientId || !jobId) return <p className="text-muted-foreground">Missing client/job id.</p>
  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumbs={[
          { label: "Clients", to: "/clients" },
          { label: client?.name ?? "Client", to: `/clients/${clientId}` },
          { label: "Ingestion" },
        ]}
        title="Ingestion job"
      />
      <IngestionWizard prJobId={jobId} clientId={clientId} />
    </div>
  )
}
