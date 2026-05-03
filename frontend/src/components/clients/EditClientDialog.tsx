import { toast } from "sonner"

import { ClientForm } from "@/components/clients/ClientForm"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useUpdateClient } from "@/hooks/useClients"
import type { Client, ClientFormInput } from "@/types/client"

interface Props {
  client: Client
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function EditClientDialog({ client, open, onOpenChange }: Props) {
  const updateClient = useUpdateClient()

  async function handleSubmit(values: ClientFormInput) {
    try {
      await updateClient.mutateAsync({ id: client.id, input: values })
      toast.success(`${values.name} updated.`)
      onOpenChange(false)
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error"
      toast.error(`Could not update client: ${message}`)
    }
  }

  // Pull only the form-relevant fields from the client row as defaults.
  const defaultValues: Partial<ClientFormInput> = {
    name: client.name,
    name_bn: client.name_bn ?? "",
    tin: client.tin ?? "",
    bin: client.bin ?? "",
    entity_type: client.entity_type,
    industry: client.industry ?? "",
    fiscal_year_end: client.fiscal_year_end,
    is_vat_registered: client.is_vat_registered,
    contact_email: client.contact_email ?? "",
    contact_phone: client.contact_phone ?? "",
    notes: client.notes ?? "",
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Edit {client.name}</DialogTitle>
          <DialogDescription>
            Changing entity type will not regenerate compliance events automatically. (Phase D will add a "regenerate" button.)
          </DialogDescription>
        </DialogHeader>
        <ClientForm
          defaultValues={defaultValues}
          submitting={updateClient.isPending}
          submitLabel="Save changes"
          onSubmit={handleSubmit}
          onCancel={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  )
}
