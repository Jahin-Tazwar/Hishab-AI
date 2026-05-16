import { useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"

import { DeleteClientDialog } from "@/components/clients/DeleteClientDialog"
import { EditClientDialog } from "@/components/clients/EditClientDialog"
import { EntityTypeBadge } from "@/components/clients/EntityTypeBadge"
import { ClientCalendarTab } from "@/components/compliance/ClientCalendarTab"
import { ClientReconciliationsList } from "@/components/reconciliation/ClientReconciliationsList"
import { Button, buttonVariants } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { PageLoading } from "@/components/ui/Loading"
import { useClient } from "@/hooks/useClients"

export function ClientDetail() {
  const { id } = useParams<{ id: string }>()
  const { data: client, isLoading } = useClient(id)
  const navigate = useNavigate()
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)

  if (isLoading) {
    return <PageLoading label="Loading client…" />
  }

  if (!client) {
    return (
      <div className="space-y-4 p-8">
        <p className="text-foreground">Client not found or has been deleted.</p>
        <Link to="/clients" className="text-foreground underline">
          Back to clients
        </Link>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <Link to="/clients" className="text-sm text-muted-foreground hover:underline">
            ← Clients
          </Link>
          <h1 className="text-2xl font-bold text-foreground mt-1">{client.name}</h1>
          {client.name_bn && <p className="text-muted-foreground">{client.name_bn}</p>}
          <div className="mt-2">
            <EntityTypeBadge type={client.entity_type} />
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setEditing(true)}>
            Edit
          </Button>
          <Button variant="destructive" onClick={() => setDeleting(true)}>
            Delete
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Identifiers</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Field label="TIN" value={client.tin} mono />
            <Field label="BIN" value={client.bin} mono />
            <Field label="VAT registered" value={client.is_vat_registered ? "Yes" : "No"} />
            <Field label="Industry" value={client.industry} />
            <Field label="Fiscal year end" value={client.fiscal_year_end} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Contact</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Field label="Email" value={client.contact_email} />
            <Field label="Phone" value={client.contact_phone} />
          </CardContent>
        </Card>
      </div>

      {client.notes && (
        <Card>
          <CardHeader>
            <CardTitle>Notes</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-foreground whitespace-pre-wrap">{client.notes}</p>
          </CardContent>
        </Card>
      )}

      <ClientReconciliationsList clientId={client.id} />

      <ClientCalendarTab clientId={client.id} />

      <Card>
        <CardHeader><CardTitle>Documents & ingestion</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          <p className="text-sm text-muted-foreground">
            Upload purchase-register and supplier-export documents in any format
            (XLSX, PDF, scans, photos). We'll extract, you review, then we
            reconcile against NBR data.
          </p>
          <Link
            to={`/clients/${client.id}/ingestion/new`}
            className={buttonVariants()}
          >
            Start ingestion
          </Link>
        </CardContent>
      </Card>

      <EditClientDialog client={client} open={editing} onOpenChange={setEditing} />
      <DeleteClientDialog
        client={client}
        open={deleting}
        onOpenChange={setDeleting}
        onDeleted={() => navigate("/clients")}
      />
    </div>
  )
}

function Field({ label, value, mono }: { label: string; value: string | null | undefined; mono?: boolean }) {
  return (
    <div className="grid grid-cols-3 gap-2">
      <span className="text-muted-foreground">{label}</span>
      <span className={`col-span-2 ${mono ? "font-mono" : ""}`}>{value || "—"}</span>
    </div>
  )
}
