// frontend/src/components/compliance/OverdueClientsWidget.tsx
import { Link } from "react-router-dom"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Spinner } from "@/components/ui/Loading"
import { useOverdueByClient } from "@/hooks/useCompliance"

export function OverdueClientsWidget() {
  const { data, isLoading } = useOverdueByClient()

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Overdue by client</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Spinner /> Loading…
          </div>
        ) : !data || data.length === 0 ? (
          <p className="text-sm text-slate-500">No overdue items. 🎉</p>
        ) : (
          <ul className="divide-y rounded-md border">
            {data.map((row) => (
              <li
                key={row.client_id}
                className="flex items-center justify-between gap-3 px-3 py-2"
              >
                <Link
                  to={`/clients/${row.client_id}`}
                  className="text-sm font-medium text-slate-900 hover:underline"
                >
                  {row.client_name}
                </Link>
                <span className="rounded-md bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800">
                  {row.overdue_count} overdue
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
