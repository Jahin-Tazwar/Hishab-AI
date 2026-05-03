import { useState } from "react"

import { AddClientDialog } from "@/components/clients/AddClientDialog"
import { ClientsTable } from "@/components/clients/ClientsTable"
import { Input } from "@/components/ui/input"
import { useClientsList } from "@/hooks/useClients"

export function Clients() {
  const [search, setSearch] = useState("")
  const { data: clients = [], isLoading } = useClientsList(search)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Clients</h1>
          <p className="text-slate-600 mt-1">
            Manage your firm's clients. Compliance deadlines are auto-generated on add.
          </p>
        </div>
        <AddClientDialog />
      </div>

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
