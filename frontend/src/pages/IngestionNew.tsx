import { useParams } from "react-router-dom"

import { UploadStep } from "@/components/ingestion/UploadStep"
import { PageHeader } from "@/components/layout/PageHeader"
import { useClient } from "@/hooks/useClients"

export function IngestionNew() {
  const { id: clientId } = useParams<{ id: string }>()
  const { data: client } = useClient(clientId)
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
        subtitle="Upload purchase-register or supplier-export documents in any format. We'll extract, you review, then finalize."
      />
      <UploadStep clientId={clientId} />
    </div>
  )
}
