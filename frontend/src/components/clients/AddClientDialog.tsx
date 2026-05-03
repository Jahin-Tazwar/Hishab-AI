import { useState } from "react"
import { toast } from "sonner"

import { ClientForm } from "@/components/clients/ClientForm"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { useCreateClient } from "@/hooks/useClients"
import type { ClientFormInput } from "@/types/client"

export function AddClientDialog() {
  const [open, setOpen] = useState(false)
  const createClient = useCreateClient()

  async function handleSubmit(values: ClientFormInput) {
    try {
      const { client, eventsGenerated } = await createClient.mutateAsync(values)
      if (eventsGenerated === null) {
        toast.warning(
          `${client.name} added, but compliance events could not be generated. You can retry from the client page.`,
        )
      } else {
        toast.success(`${client.name} added (${eventsGenerated} compliance events generated).`)
      }
      setOpen(false)
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error"
      toast.error(`Could not add client: ${message}`)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>Add client</Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Add a new client</DialogTitle>
          <DialogDescription>
            Compliance deadlines for the next 12 months will be auto-generated based on the entity type.
          </DialogDescription>
        </DialogHeader>
        <ClientForm
          submitting={createClient.isPending}
          submitLabel="Add client"
          onSubmit={handleSubmit}
          onCancel={() => setOpen(false)}
        />
      </DialogContent>
    </Dialog>
  )
}
