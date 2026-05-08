// frontend/src/components/compliance/UpcomingDeadlinesWidget.tsx
import { Link } from "react-router-dom"

import { EventStatusBadge } from "@/components/compliance/EventStatusBadge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useUpcomingEvents } from "@/hooks/useCompliance"
import { groupByWeek } from "@/lib/groupByWeek"
import { isOverdue } from "@/lib/isOverdue"
import { obligationLabel } from "@/lib/obligationLabels"
import type { ComplianceEventWithClient } from "@/types/compliance"

export function UpcomingDeadlinesWidget() {
  const { data, isLoading } = useUpcomingEvents(30)
  const today = new Date()
  const buckets = groupByWeek(data ?? [], today, (e) => e.due_date)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Upcoming deadlines (next 30 days)</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading ? (
          <p className="text-sm text-slate-500">Loading…</p>
        ) : (data ?? []).length === 0 ? (
          <p className="text-sm text-slate-500">
            No deadlines in the next 30 days. Add a client to populate the calendar.
          </p>
        ) : (
          <>
            <Section title="This week" rows={buckets.thisWeek} today={today} />
            <Section title="Next week" rows={buckets.nextWeek} today={today} />
            <Section title="Weeks 3–4" rows={buckets.weeksThreeAndFour} today={today} />
          </>
        )}
      </CardContent>
    </Card>
  )
}

function Section({
  title, rows, today,
}: { title: string; rows: ComplianceEventWithClient[]; today: Date }) {
  if (rows.length === 0) return null
  return (
    <div className="space-y-1.5">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{title}</p>
      <ul className="divide-y rounded-md border">
        {rows.map((e) => {
          const derivedStatus = isOverdue(e, today) ? "overdue" : e.status
          return (
            <li key={e.id} className="flex items-center justify-between gap-3 px-3 py-2">
              <div className="min-w-0 flex-1">
                <Link
                  to={`/clients/${e.client_id}`}
                  className="text-sm font-medium text-slate-900 hover:underline"
                >
                  {e.client_name}
                </Link>
                <p className="truncate text-xs text-slate-500">
                  {obligationLabel(e.obligation_type)}
                </p>
              </div>
              <span className="text-xs text-slate-600">{e.due_date}</span>
              <EventStatusBadge status={derivedStatus} />
            </li>
          )
        })}
      </ul>
    </div>
  )
}
