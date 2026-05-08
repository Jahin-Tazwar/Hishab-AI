import { useState } from "react"
import { Link, useParams } from "react-router-dom"

import { DeleteClientDialog } from "@/components/clients/DeleteClientDialog"
import { EditClientDialog } from "@/components/clients/EditClientDialog"
import { EntityTypeBadge } from "@/components/clients/EntityTypeBadge"
import { ClientCalendarTab } from "@/components/compliance/ClientCalendarTab"
import { ClientReconciliationsList } from "@/components/reconciliation/ClientReconciliationsList"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useClient } from "@/hooks/useClients"

export function ClientDetail() {
  const { id } = useParams<{ id: string }>()
  const { data: client, isLoading } = useClient(id)
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)

  if (isLoading) {
    return <div className="text-slate-500 p-8">Loading client…</div>
  }

  if (!client) {
    return (
      <div className="space-y-4 p-8">
        <p className="text-slate-700">Client not found or has been deleted.</p>
        <Link to="/clients" className="text-slate-900 underline">
          Back to clients
        </Link>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <Link to="/clients" className="text-sm text-slate-500 hover:underline">
            ← Clients
          </Link>
          <h1 className="text-2xl font-bold text-slate-900 mt-1">{client.name}</h1>
          {client.name_bn && <p className="text-slate-600">{client.name_bn}</p>}
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
            <p className="text-sm text-slate-700 whitespace-pre-wrap">{client.notes}</p>
          </CardContent>
        </Card>
      )}

      <ClientReconciliationsList clientId={client.id} />

      <ClientCalendarTab clientId={client.id} />

      <div className="border-t pt-6">
        <h2 className="text-lg font-semibold text-slate-900">Coming in later phases</h2>
        <p className="text-sm text-slate-600 mt-1">
          Documents tab (file uploads beyond reconciliation) ships in a later phase.
        </p>
      </div>

      <EditClientDialog client={client} open={editing} onOpenChange={setEditing} />
      <DeleteClientDialog
        client={client}
        open={deleting}
        onOpenChange={setDeleting}
        onDeleted={() => {
          // Navigate back to list after delete
          window.location.href = "/clients"
        }}
      />
    </div>
  )
}

function Field({ label, value, mono }: { label: string; value: string | null | undefined; mono?: boolean }) {
  return (
    <div className="grid grid-cols-3 gap-2">
      <span className="text-slate-500">{label}</span>
      <span className={`col-span-2 ${mono ? "font-mono" : ""}`}>{value || "—"}</span>
    </div>
  )
}
