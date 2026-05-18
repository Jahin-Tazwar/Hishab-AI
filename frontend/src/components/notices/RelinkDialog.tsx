import { useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { useClientsList } from "@/hooks/useClients"
import { useRelinkNotice } from "@/hooks/useNotices"
import { ApiError } from "@/lib/api"
import type { Notice } from "@/types/notices"

interface Props {
  notice: Notice
  open: boolean
  onOpenChange: (o: boolean) => void
}

export function RelinkDialog({ notice, open, onOpenChange }: Props) {
  const clients = useClientsList()
  const relink = useRelinkNotice(notice.id)
  const [clientId, setClientId] = useState<string>(notice.client_id ?? "")
  const [start, setStart] = useState<string>(notice.period_start ?? "")
  const [end, setEnd] = useState<string>(notice.period_end ?? "")

  async function save() {
    try {
      await relink.mutateAsync({
        client_id: clientId, period_start: start, period_end: end,
      })
      toast.success("Notice re-linked. Re-running the linker…")
      onOpenChange(false)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : (e as Error).message)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Link this notice</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="rl-client">Client</Label>
            <Select value={clientId} onValueChange={setClientId}>
              <SelectTrigger id="rl-client"><SelectValue placeholder="Pick a client" /></SelectTrigger>
              <SelectContent>
                {(clients.data ?? []).map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.name}{c.bin ? ` (${c.bin})` : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="rl-start">Period start</Label>
              <Input id="rl-start" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="rl-end">Period end</Label>
              <Input id="rl-end" type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={save} disabled={!clientId || !start || !end || relink.isPending}>
            {relink.isPending ? "Saving…" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
