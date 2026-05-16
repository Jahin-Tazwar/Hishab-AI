import { useState } from "react"

import { AddClientDialog } from "@/components/clients/AddClientDialog"
import { ClientsTable } from "@/components/clients/ClientsTable"
import { PageHeader } from "@/components/layout/PageHeader"
import { Input } from "@/components/ui/input"
import { useClientsList } from "@/hooks/useClients"
import { useDebouncedValue } from "@/hooks/useDebouncedValue"

export function Clients() {
  const [search, setSearch] = useState("")
  const debounced = useDebouncedValue(search, 250)
  const { data: clients = [], isLoading } = useClientsList(debounced)

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
        autoFocus
      />
      <ClientsTable clients={clients} isLoading={isLoading} />
    </div>
  )
}
