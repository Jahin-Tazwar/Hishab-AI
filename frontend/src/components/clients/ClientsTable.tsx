import { Link } from "react-router-dom"
import { useState } from "react"
import { MoreHorizontal } from "lucide-react"

import { DeleteClientDialog } from "@/components/clients/DeleteClientDialog"
import { EditClientDialog } from "@/components/clients/EditClientDialog"
import { EntityTypeBadge } from "@/components/clients/EntityTypeBadge"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { Client } from "@/types/client"

interface Props {
  clients: Client[]
  isLoading: boolean
}

export function ClientsTable({ clients, isLoading }: Props) {
  const [editing, setEditing] = useState<Client | null>(null)
  const [deleting, setDeleting] = useState<Client | null>(null)

  if (isLoading) {
    return <div className="text-slate-500 py-8 text-center">Loading clients…</div>
  }

  if (clients.length === 0) {
    return (
      <div className="text-slate-500 py-12 text-center border border-dashed rounded">
        No clients yet. Add your first client using the button above.
      </div>
    )
  }

  return (
    <>
      <div className="rounded border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Entity type</TableHead>
              <TableHead>BIN</TableHead>
              <TableHead>TIN</TableHead>
              <TableHead>VAT registered</TableHead>
              <TableHead className="w-12" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {clients.map((c) => (
              <TableRow key={c.id}>
                <TableCell>
                  <Link to={`/clients/${c.id}`} className="font-medium text-slate-900 hover:underline">
                    {c.name}
                  </Link>
                  {c.name_bn && <div className="text-xs text-slate-500">{c.name_bn}</div>}
                </TableCell>
                <TableCell>
                  <EntityTypeBadge type={c.entity_type} />
                </TableCell>
                <TableCell className="font-mono text-sm">{c.bin ?? "—"}</TableCell>
                <TableCell className="font-mono text-sm">{c.tin ?? "—"}</TableCell>
                <TableCell>{c.is_vat_registered ? "Yes" : "No"}</TableCell>
                <TableCell>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="sm">
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onClick={() => setEditing(c)}>Edit</DropdownMenuItem>
                      <DropdownMenuItem
                        className="text-red-600 focus:text-red-700"
                        onClick={() => setDeleting(c)}
                      >
                        Delete
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {editing && (
        <EditClientDialog
          client={editing}
          open={Boolean(editing)}
          onOpenChange={(o) => !o && setEditing(null)}
        />
      )}
      {deleting && (
        <DeleteClientDialog
          client={deleting}
          open={Boolean(deleting)}
          onOpenChange={(o) => !o && setDeleting(null)}
        />
      )}
    </>
  )
}
