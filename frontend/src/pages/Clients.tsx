import { useState } from "react"

import { AddClientDialog } from "@/components/clients/AddClientDialog"
import { ClientsTable } from "@/components/clients/ClientsTable"
import { PageHeader } from "@/components/layout/PageHeader"
import { Input } from "@/components/ui/input"
import { useClientsList } from "@/hooks/useClients"

export function Clients() {
  const [search, setSearch] = useState("")
  const { data: clients = [], isLoading } = useClientsList(search)

  return (
    <div className="space-y-6">
      <PageHeader
        title="Clients"
        subtitle="Manage your firm's clients. Compliance deadlines are auto-generated on add."
        actions={<AddClientDialog />}
      />
      <Input
        placeholder="Search by name…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="max-w-sm"
      />
      <ClientsTable clients={clients} isLoading={isLoading} />
    </div>
  )
}
