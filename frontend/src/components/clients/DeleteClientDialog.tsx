import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useDeleteClient } from "@/hooks/useClients"
import type { Client } from "@/types/client"

interface Props {
  client: Client
  open: boolean
  onOpenChange: (open: boolean) => void
  onDeleted?: () => void
}

export function DeleteClientDialog({ client, open, onOpenChange, onDeleted }: Props) {
  const deleteClient = useDeleteClient()

  async function handleConfirm() {
    try {
      await deleteClient.mutateAsync(client.id)
      toast.success(`${client.name} deleted.`)
      onOpenChange(false)
      onDeleted?.()
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error"
      toast.error(`Could not delete client: ${message}`)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete {client.name}?</DialogTitle>
          <DialogDescription>
            This is a soft delete — the record stays in the database for audit purposes,
            but will be hidden from lists. Compliance events for this client will still
            count against your upcoming deadlines view until they are also archived.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={deleteClient.isPending}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleConfirm}
            disabled={deleteClient.isPending}
          >
            {deleteClient.isPending ? "Deleting…" : "Delete"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
