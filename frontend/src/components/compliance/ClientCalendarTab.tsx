import { useState } from "react"

import { EventStatusBadge } from "@/components/compliance/EventStatusBadge"
import { EventStatusSelect } from "@/components/compliance/EventStatusSelect"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import { useClientEvents } from "@/hooks/useCompliance"
import { isOverdue } from "@/lib/isOverdue"
import { obligationLabel } from "@/lib/obligationLabels"
import { EVENT_STATUS_LABELS, type EventStatus } from "@/types/compliance"

interface Props {
  clientId: string
}

const FILTERS: ("all" | EventStatus)[] = [
  "all", "pending", "filed", "overdue", "waived", "na",
]

export function ClientCalendarTab({ clientId }: Props) {
  const [filter, setFilter] = useState<typeof FILTERS[number]>("all")
  const { data, isLoading } = useClientEvents(clientId, filter)
  const today = new Date()

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Compliance calendar</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-1">
          {FILTERS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setFilter(s)}
              className={`rounded-md border px-2.5 py-1 text-xs ${
                filter === s
                  ? "border-slate-900 bg-slate-900 text-white"
                  : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
              }`}
            >
              {s === "all" ? "All" : EVENT_STATUS_LABELS[s]}
            </button>
          ))}
        </div>

        {isLoading ? (
          <p className="text-sm text-slate-500">Loading…</p>
        ) : !data || data.length === 0 ? (
          <p className="text-sm text-slate-500">
            {filter === "all"
              ? "No compliance events for this client. Events generate from the obligations seeded for the client's entity type and VAT registration."
              : "No matching events for this filter."}
          </p>
        ) : (
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Obligation</TableHead>
                  <TableHead>Period</TableHead>
                  <TableHead>Due</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.map((e) => {
                  const derived = isOverdue(e, today) ? "overdue" : e.status
                  return (
                    <TableRow key={e.id}>
                      <TableCell>{obligationLabel(e.obligation_type)}</TableCell>
                      <TableCell className="text-slate-600">
                        {e.period_start} → {e.period_end}
                      </TableCell>
                      <TableCell>{e.due_date}</TableCell>
                      <TableCell>
                        <EventStatusBadge status={derived} />
                      </TableCell>
                      <TableCell className="text-right">
                        <EventStatusSelect eventId={e.id} current={e.status} />
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
