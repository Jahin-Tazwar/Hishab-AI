# Phase D — Calendar + Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface the existing `compliance_events` data via a Dashboard (Upcoming / Overdue / Recent recons widgets) and a Calendar tab on the client detail page with inline status updates. Polish empty states across the app.

**Architecture:** Frontend-only phase. Direct Supabase reads/writes via TanStack Query (RLS handles tenant isolation; the audit trigger captures the user automatically through PostgREST's JWT-claim handoff). Overdue is derived in queries (`status='pending' AND due_date < today`), not materialised — no scheduler. Calendar is a table view per the master spec; monthly grid is deferred.

**Tech Stack:** React 18 + TypeScript + Vite, Vitest + @testing-library/react, TanStack Query 5, supabase-js, shadcn/ui (Radix Select / Card / Table), sonner toasts, Tailwind.

**Reference spec:** `docs/superpowers/specs/2026-05-08-phase-d-calendar-dashboard-design.md`

---

## File map

```
frontend/src/
  hooks/
    useCompliance.ts                                     [NEW — D1, D2]
  components/compliance/
    EventStatusBadge.tsx                                 [NEW — D3]
    EventStatusSelect.tsx                                [NEW — D4]
    UpcomingDeadlinesWidget.tsx                          [NEW — D6]
    OverdueClientsWidget.tsx                             [NEW — D7]
    RecentReconciliationsWidget.tsx                      [NEW — D8]
    ClientCalendarTab.tsx                                [NEW — D10]
  lib/
    obligationLabels.ts                                  [NEW — D3]
    groupByWeek.ts                                       [NEW — D5]
    isOverdue.ts                                         [NEW — D5]
    __tests__/
      groupByWeek.test.ts                                [NEW — D5]
      isOverdue.test.ts                                  [NEW — D5]
  types/
    compliance.ts                                        [NEW — D1]
  pages/
    Dashboard.tsx                                        [REWRITE — D9]
    ClientDetail.tsx                                     [EDIT — D11]
```

No backend or migration changes.

---

## Task D1: Compliance types

**Files:**
- Create: `frontend/src/types/compliance.ts`

- [ ] **Step 1: Define the row + status types**

```ts
// frontend/src/types/compliance.ts

/**
 * compliance_events row shape mirrored from the Supabase schema
 * (see migrations/0002_tenant_tables.sql).
 *
 * Note: status enum includes "overdue" but Phase D never writes it —
 * we derive overdue in queries from (status='pending' AND due_date<today).
 */
export const EVENT_STATUSES = [
  "pending",
  "filed",
  "overdue",
  "waived",
  "na",
] as const
export type EventStatus = (typeof EVENT_STATUSES)[number]

export const EVENT_STATUS_LABELS: Record<EventStatus, string> = {
  pending: "Pending",
  filed: "Filed",
  overdue: "Overdue",
  waived: "Waived",
  na: "N/A",
}

/** Statuses a CA can pick from the inline select. Excludes "overdue" (derived). */
export const SELECTABLE_STATUSES: EventStatus[] = [
  "pending",
  "filed",
  "waived",
  "na",
]

export interface ComplianceEventRow {
  id: string
  tenant_id: string
  client_id: string
  obligation_type: string
  period_start: string   // YYYY-MM-DD
  period_end: string
  due_date: string
  status: EventStatus
  filed_date: string | null
  notes: string | null
  created_at: string
  updated_at: string
}

/** Row enriched with the joined client name (for cross-tenant Dashboard widgets). */
export interface ComplianceEventWithClient extends ComplianceEventRow {
  client_name: string
}

/** Aggregate row for the OverdueClientsWidget. */
export interface OverdueByClient {
  client_id: string
  client_name: string
  overdue_count: number
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/types/compliance.ts
git commit -m "feat(compliance): row + status types for Phase D"
```

---

## Task D2: TanStack Query hooks

**Files:**
- Create: `frontend/src/hooks/useCompliance.ts`

- [ ] **Step 1: Write the hooks file**

```ts
// frontend/src/hooks/useCompliance.ts
/**
 * Compliance / calendar query hooks.
 *
 * All reads scoped automatically by RLS. Status writes go directly to
 * Supabase — the audit trigger captures the user via PostgREST's
 * automatic request.jwt.claim.sub setting.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { supabase } from "@/lib/supabase"
import type {
  ComplianceEventRow,
  ComplianceEventWithClient,
  EventStatus,
  OverdueByClient,
} from "@/types/compliance"
import type { ReconciliationRow } from "@/types/reconciliation"

export const complianceKeys = {
  all: ["compliance"] as const,
  upcoming: (days: number) => ["compliance", "upcoming", days] as const,
  byClient: (clientId: string, status: string) =>
    ["compliance", "by-client", clientId, status] as const,
  overdueByClient: () => ["compliance", "overdue-by-client"] as const,
  recentReconciliations: (limit: number) =>
    ["compliance", "recent-reconciliations", limit] as const,
}

function _todayISO(): string {
  return new Date().toISOString().slice(0, 10)
}

function _addDaysISO(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}

/** Events with due_date in [today, today+daysAhead], joined to client name. */
export function useUpcomingEvents(daysAhead = 30) {
  return useQuery({
    queryKey: complianceKeys.upcoming(daysAhead),
    queryFn: async (): Promise<ComplianceEventWithClient[]> => {
      const { data, error } = await supabase
        .from("compliance_events")
        .select("*, clients!inner(name)")
        .gte("due_date", _todayISO())
        .lte("due_date", _addDaysISO(daysAhead))
        .order("due_date", { ascending: true })
      if (error) throw error
      // Supabase returns the joined row as { ..., clients: { name } }
      return (data ?? []).map((row: ComplianceEventRow & { clients: { name: string } }) => {
        const { clients, ...rest } = row
        return { ...rest, client_name: clients.name }
      })
    },
  })
}

/** All events for one client; optional status filter; due-date ascending. */
export function useClientEvents(
  clientId: string | undefined,
  status: EventStatus | "all" = "all",
) {
  return useQuery({
    queryKey: complianceKeys.byClient(clientId ?? "", status),
    enabled: Boolean(clientId),
    queryFn: async (): Promise<ComplianceEventRow[]> => {
      if (!clientId) return []
      let q = supabase
        .from("compliance_events")
        .select("*")
        .eq("client_id", clientId)
        .order("due_date", { ascending: true })
      if (status !== "all" && status !== "overdue") {
        q = q.eq("status", status)
      } else if (status === "overdue") {
        q = q.eq("status", "pending").lt("due_date", _todayISO())
      }
      const { data, error } = await q
      if (error) throw error
      return (data ?? []) as ComplianceEventRow[]
    },
  })
}

/**
 * Counts of (status='pending' AND due_date<today) grouped by client.
 * Implementation: fetch the rows + reduce on the client. Volume is small
 * (one row per overdue obligation per client), and this avoids
 * RLS-edge-case issues with PostgREST aggregates.
 */
export function useOverdueByClient() {
  return useQuery({
    queryKey: complianceKeys.overdueByClient(),
    queryFn: async (): Promise<OverdueByClient[]> => {
      const { data, error } = await supabase
        .from("compliance_events")
        .select("client_id, clients!inner(name)")
        .eq("status", "pending")
        .lt("due_date", _todayISO())
      if (error) throw error
      const byClient = new Map<string, OverdueByClient>()
      for (const row of data ?? []) {
        const r = row as { client_id: string; clients: { name: string } }
        const existing = byClient.get(r.client_id)
        if (existing) {
          existing.overdue_count += 1
        } else {
          byClient.set(r.client_id, {
            client_id: r.client_id,
            client_name: r.clients.name,
            overdue_count: 1,
          })
        }
      }
      return [...byClient.values()].sort(
        (a, b) => b.overdue_count - a.overdue_count,
      )
    },
  })
}

/** Most-recent reconciliations across the tenant (joined to client name). */
export function useRecentReconciliations(limit = 5) {
  return useQuery({
    queryKey: complianceKeys.recentReconciliations(limit),
    queryFn: async (): Promise<(ReconciliationRow & { client_name: string })[]> => {
      const { data, error } = await supabase
        .from("vat_reconciliations")
        .select("*, clients!inner(name)")
        .order("started_at", { ascending: false })
        .limit(limit)
      if (error) throw error
      return (data ?? []).map((row: ReconciliationRow & { clients: { name: string } }) => {
        const { clients, ...rest } = row
        return { ...rest, client_name: clients.name }
      })
    },
  })
}

/**
 * Update a single event's status.
 *  - status='filed' → filed_date = today
 *  - any other status → filed_date = null
 *
 * Invalidates all compliance keys; the small over-fetch keeps the UI
 * trivially correct after status changes that affect multiple widgets.
 */
export function useUpdateEventStatus() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      id,
      status,
      notes,
    }: {
      id: string
      status: EventStatus
      notes?: string | null
    }): Promise<ComplianceEventRow> => {
      const update: Partial<ComplianceEventRow> = {
        status,
        filed_date: status === "filed" ? _todayISO() : null,
      }
      if (notes !== undefined) update.notes = notes
      const { data, error } = await supabase
        .from("compliance_events")
        .update(update)
        .eq("id", id)
        .select()
        .single()
      if (error) throw error
      return data as ComplianceEventRow
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: complianceKeys.all })
    },
  })
}
```

- [ ] **Step 2: Verify TypeScript**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0, no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useCompliance.ts
git commit -m "feat(compliance): TanStack Query hooks for events + recent recons"
```

---

## Task D3: Obligation labels + EventStatusBadge

**Files:**
- Create: `frontend/src/lib/obligationLabels.ts`
- Create: `frontend/src/components/compliance/EventStatusBadge.tsx`

- [ ] **Step 1: Write obligation label map**

```ts
// frontend/src/lib/obligationLabels.ts
/**
 * Display labels for the 6 seeded obligation types.
 * See migrations/0008_seed_obligations.sql for the source of truth.
 *
 * Falls back to a humanised version of the raw type for any unknown
 * obligation_type encountered (defensive — schema can grow).
 */
const LABELS: Record<string, string> = {
  vat_return: "VAT Return (Mushak 9.1)",
  tds_return: "TDS Return",
  tds_deposit: "TDS Challan Deposit",
  income_tax_company: "Company Income Tax Return",
  income_tax_individual: "Individual Income Tax Return",
  rjsc_annual: "RJSC Annual Return",
}

export function obligationLabel(type: string): string {
  if (LABELS[type]) return LABELS[type]
  // Unknown → humanise: "foo_bar_baz" → "Foo Bar Baz"
  return type
    .split("_")
    .map((w) => (w.length ? w[0].toUpperCase() + w.slice(1) : w))
    .join(" ")
}
```

- [ ] **Step 2: Write the badge component**

```tsx
// frontend/src/components/compliance/EventStatusBadge.tsx
import { Badge } from "@/components/ui/badge"
import { EVENT_STATUS_LABELS, type EventStatus } from "@/types/compliance"

const STYLE: Record<EventStatus, string> = {
  pending: "bg-slate-100 text-slate-800 hover:bg-slate-100",
  filed: "bg-green-100 text-green-800 hover:bg-green-100",
  overdue: "bg-red-100 text-red-800 hover:bg-red-100",
  waived: "bg-slate-200 text-slate-700 hover:bg-slate-200",
  na: "bg-slate-200 text-slate-500 italic hover:bg-slate-200",
}

export function EventStatusBadge({ status }: { status: EventStatus }) {
  return (
    <Badge variant="secondary" className={STYLE[status]}>
      {EVENT_STATUS_LABELS[status]}
    </Badge>
  )
}
```

- [ ] **Step 3: Verify TypeScript**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/obligationLabels.ts frontend/src/components/compliance/EventStatusBadge.tsx
git commit -m "feat(compliance): obligation label helper + EventStatusBadge"
```

---

## Task D4: EventStatusSelect (inline status mutation)

**Files:**
- Create: `frontend/src/components/compliance/EventStatusSelect.tsx`

- [ ] **Step 1: Write the inline select**

```tsx
// frontend/src/components/compliance/EventStatusSelect.tsx
import { useState } from "react"
import { toast } from "sonner"

import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { useUpdateEventStatus } from "@/hooks/useCompliance"
import {
  EVENT_STATUS_LABELS, SELECTABLE_STATUSES, type EventStatus,
} from "@/types/compliance"

interface Props {
  eventId: string
  /**
   * Effective status for display. When the row is derived-overdue
   * (pending + due_date<today), the parent may pass "overdue" — but
   * the dropdown itself only lets the user choose from
   * SELECTABLE_STATUSES (pending/filed/waived/na). Choosing one
   * clears the derived-overdue badge naturally.
   */
  current: EventStatus
  disabled?: boolean
}

export function EventStatusSelect({ eventId, current, disabled }: Props) {
  const update = useUpdateEventStatus()
  // For "overdue" (derived) we still let the underlying value be pending so
  // the select shows the actionable state.
  const initial: EventStatus = current === "overdue" ? "pending" : current
  const [value, setValue] = useState<EventStatus>(initial)

  async function handleChange(next: string) {
    const status = next as EventStatus
    setValue(status)
    try {
      await update.mutateAsync({ id: eventId, status })
      toast.success(`Marked ${EVENT_STATUS_LABELS[status].toLowerCase()}`)
    } catch (e) {
      // Revert on failure
      setValue(initial)
      toast.error(e instanceof Error ? e.message : "Update failed")
    }
  }

  return (
    <Select
      value={value}
      onValueChange={handleChange}
      disabled={disabled || update.isPending}
    >
      <SelectTrigger className="h-7 w-32 text-xs">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {SELECTABLE_STATUSES.map((s) => (
          <SelectItem key={s} value={s}>
            {EVENT_STATUS_LABELS[s]}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/compliance/EventStatusSelect.tsx
git commit -m "feat(compliance): EventStatusSelect inline mutation"
```

---

## Task D5: groupByWeek + isOverdue helpers (with unit tests)

**Files:**
- Create: `frontend/src/lib/groupByWeek.ts`
- Create: `frontend/src/lib/isOverdue.ts`
- Create: `frontend/src/lib/__tests__/groupByWeek.test.ts`
- Create: `frontend/src/lib/__tests__/isOverdue.test.ts`

- [ ] **Step 1: Write the failing tests for groupByWeek**

```ts
// frontend/src/lib/__tests__/groupByWeek.test.ts
import { describe, expect, it } from "vitest"

import { groupByWeek } from "../groupByWeek"

interface T { due_date: string }

const today = new Date("2024-06-10") // Monday

describe("groupByWeek", () => {
  it("returns empty buckets for empty input", () => {
    const r = groupByWeek<T>([], today, (e) => e.due_date)
    expect(r.thisWeek).toEqual([])
    expect(r.nextWeek).toEqual([])
    expect(r.weeksThreeAndFour).toEqual([])
  })

  it("places today in thisWeek", () => {
    const r = groupByWeek<T>([{ due_date: "2024-06-10" }], today, (e) => e.due_date)
    expect(r.thisWeek).toHaveLength(1)
  })

  it("places end-of-this-week in thisWeek (Sunday boundary)", () => {
    // Mon-start week: Mon Jun 10 → Sun Jun 16 inclusive
    const r = groupByWeek<T>([{ due_date: "2024-06-16" }], today, (e) => e.due_date)
    expect(r.thisWeek).toHaveLength(1)
    expect(r.nextWeek).toHaveLength(0)
  })

  it("places start-of-next-week in nextWeek", () => {
    const r = groupByWeek<T>([{ due_date: "2024-06-17" }], today, (e) => e.due_date)
    expect(r.thisWeek).toHaveLength(0)
    expect(r.nextWeek).toHaveLength(1)
  })

  it("places weeks 3 and 4 (days 14-27 from today) in weeksThreeAndFour", () => {
    const r = groupByWeek<T>(
      [{ due_date: "2024-06-24" }, { due_date: "2024-07-07" }],
      today,
      (e) => e.due_date,
    )
    // Jun 24 = day 14 → weeksThreeAndFour
    // Jul 7  = day 27 → weeksThreeAndFour
    expect(r.weeksThreeAndFour).toHaveLength(2)
  })

  it("ignores past dates and dates beyond 28 days", () => {
    const r = groupByWeek<T>(
      [{ due_date: "2024-06-09" }, { due_date: "2024-07-09" }],
      today,
      (e) => e.due_date,
    )
    expect(r.thisWeek).toHaveLength(0)
    expect(r.nextWeek).toHaveLength(0)
    expect(r.weeksThreeAndFour).toHaveLength(0)
  })
})
```

- [ ] **Step 2: Run the failing test**

Run: `cd frontend && npx vitest run src/lib/__tests__/groupByWeek.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement groupByWeek**

```ts
// frontend/src/lib/groupByWeek.ts
/**
 * Group items by which of the next four weeks their date falls in,
 * using a Monday-start week convention.
 *
 * Buckets:
 *   thisWeek            — today through Sunday of this week
 *   nextWeek            — Monday-Sunday of the week after
 *   weeksThreeAndFour   — the following 14 days
 *
 * Anything before today or beyond 28 days is dropped.
 */
export interface WeekBuckets<T> {
  thisWeek: T[]
  nextWeek: T[]
  weeksThreeAndFour: T[]
}

function _toMidnight(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate())
}

/** Sunday of the current week, treating Monday as the start. */
function _endOfThisWeek(today: Date): Date {
  const t = _toMidnight(today)
  // JS getDay(): Sun=0, Mon=1, ... Sat=6. Days until Sunday (Mon-start week):
  //   Mon=6, Tue=5, Wed=4, Thu=3, Fri=2, Sat=1, Sun=0
  const dow = t.getDay()
  const daysUntilSun = dow === 0 ? 0 : 7 - dow
  const out = new Date(t)
  out.setDate(t.getDate() + daysUntilSun)
  return out
}

export function groupByWeek<T>(
  items: T[],
  today: Date,
  getDate: (item: T) => string,
): WeekBuckets<T> {
  const start = _toMidnight(today).getTime()
  const endThis = _endOfThisWeek(today).getTime()
  const endNext = endThis + 7 * 86_400_000
  const endFour = endThis + 21 * 86_400_000

  const buckets: WeekBuckets<T> = {
    thisWeek: [],
    nextWeek: [],
    weeksThreeAndFour: [],
  }
  for (const it of items) {
    const ts = _toMidnight(new Date(getDate(it))).getTime()
    if (ts < start) continue
    if (ts <= endThis) buckets.thisWeek.push(it)
    else if (ts <= endNext) buckets.nextWeek.push(it)
    else if (ts <= endFour) buckets.weeksThreeAndFour.push(it)
  }
  return buckets
}
```

- [ ] **Step 4: Run tests, verify pass**

Run: `cd frontend && npx vitest run src/lib/__tests__/groupByWeek.test.ts`
Expected: 6 passed.

- [ ] **Step 5: Write the failing tests for isOverdue**

```ts
// frontend/src/lib/__tests__/isOverdue.test.ts
import { describe, expect, it } from "vitest"

import { isOverdue } from "../isOverdue"

const today = new Date("2024-06-10")

describe("isOverdue", () => {
  it("is true for pending events past due", () => {
    expect(isOverdue({ status: "pending", due_date: "2024-06-09" }, today)).toBe(true)
  })

  it("is false for pending events due today", () => {
    expect(isOverdue({ status: "pending", due_date: "2024-06-10" }, today)).toBe(false)
  })

  it("is false for pending events due in the future", () => {
    expect(isOverdue({ status: "pending", due_date: "2024-06-11" }, today)).toBe(false)
  })

  it("is false for filed events even past due", () => {
    expect(isOverdue({ status: "filed", due_date: "2024-06-01" }, today)).toBe(false)
  })

  it("is false for waived events", () => {
    expect(isOverdue({ status: "waived", due_date: "2024-06-01" }, today)).toBe(false)
  })

  it("is false for na events", () => {
    expect(isOverdue({ status: "na", due_date: "2024-06-01" }, today)).toBe(false)
  })
})
```

- [ ] **Step 6: Run the failing test**

Run: `cd frontend && npx vitest run src/lib/__tests__/isOverdue.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 7: Implement isOverdue**

```ts
// frontend/src/lib/isOverdue.ts
import type { EventStatus } from "@/types/compliance"

interface Eventish {
  status: EventStatus
  due_date: string
}

/**
 * Derived "overdue" check used by the UI. A row is overdue when status
 * is "pending" and the due_date is strictly before today.
 *
 * `today` is passed in (rather than computed) so callers can keep a
 * single reference date for a render — keeps "Are these all overdue?"
 * answers stable across the same view.
 */
export function isOverdue(event: Eventish, today: Date): boolean {
  if (event.status !== "pending") return false
  const t = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime()
  const due = new Date(event.due_date).getTime()
  return due < t
}
```

- [ ] **Step 8: Run tests, verify pass**

Run: `cd frontend && npx vitest run src/lib/__tests__/isOverdue.test.ts`
Expected: 6 passed.

- [ ] **Step 9: Run full Vitest suite to verify no regressions**

Run: `cd frontend && npm test`
Expected: all suites pass.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/lib/groupByWeek.ts frontend/src/lib/isOverdue.ts frontend/src/lib/__tests__/groupByWeek.test.ts frontend/src/lib/__tests__/isOverdue.test.ts
git commit -m "feat(compliance): groupByWeek + isOverdue helpers with tests"
```

---

## Task D6: UpcomingDeadlinesWidget

**Files:**
- Create: `frontend/src/components/compliance/UpcomingDeadlinesWidget.tsx`

- [ ] **Step 1: Write the widget**

```tsx
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
```

- [ ] **Step 2: Verify TypeScript**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/compliance/UpcomingDeadlinesWidget.tsx
git commit -m "feat(compliance): UpcomingDeadlinesWidget for Dashboard"
```

---

## Task D7: OverdueClientsWidget

**Files:**
- Create: `frontend/src/components/compliance/OverdueClientsWidget.tsx`

- [ ] **Step 1: Write the widget**

```tsx
// frontend/src/components/compliance/OverdueClientsWidget.tsx
import { Link } from "react-router-dom"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
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
          <p className="text-sm text-slate-500">Loading…</p>
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
```

- [ ] **Step 2: Verify TypeScript**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/compliance/OverdueClientsWidget.tsx
git commit -m "feat(compliance): OverdueClientsWidget for Dashboard"
```

---

## Task D8: RecentReconciliationsWidget

**Files:**
- Create: `frontend/src/components/compliance/RecentReconciliationsWidget.tsx`

- [ ] **Step 1: Write the widget**

```tsx
// frontend/src/components/compliance/RecentReconciliationsWidget.tsx
import { Link } from "react-router-dom"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useRecentReconciliations } from "@/hooks/useCompliance"
import { formatBDT } from "@/lib/formatBDT"

export function RecentReconciliationsWidget() {
  const { data, isLoading } = useRecentReconciliations(5)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Recent reconciliations</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="text-sm text-slate-500">Loading…</p>
        ) : !data || data.length === 0 ? (
          <p className="text-sm text-slate-500">No reconciliations yet.</p>
        ) : (
          <ul className="divide-y rounded-md border">
            {data.map((r) => (
              <li
                key={r.id}
                className="flex items-center justify-between gap-3 px-3 py-2"
              >
                <div className="min-w-0 flex-1">
                  <Link
                    to={`/clients/${r.client_id}/recon/${r.id}`}
                    className="text-sm font-medium text-slate-900 hover:underline"
                  >
                    {r.client_name}
                  </Link>
                  <p className="text-xs text-slate-500">
                    {r.period_start} → {r.period_end}
                  </p>
                </div>
                <span className="font-mono text-xs text-red-700">
                  {formatBDT(r.at_risk_itc_bdt, { compact: true })} at risk
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/compliance/RecentReconciliationsWidget.tsx
git commit -m "feat(compliance): RecentReconciliationsWidget for Dashboard"
```

---

## Task D9: Rewrite Dashboard page

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: Replace the Dashboard with a 3-widget grid**

```tsx
// frontend/src/pages/Dashboard.tsx
import { OverdueClientsWidget } from "@/components/compliance/OverdueClientsWidget"
import { RecentReconciliationsWidget } from "@/components/compliance/RecentReconciliationsWidget"
import { UpcomingDeadlinesWidget } from "@/components/compliance/UpcomingDeadlinesWidget"
import { useUserProfile } from "@/hooks/useUserProfile"

export function Dashboard() {
  const { data: profile } = useUserProfile()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
        <p className="text-slate-600 mt-1">
          {profile?.full_name ? `Welcome back, ${profile.full_name}.` : "Welcome to HishabAI."}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <UpcomingDeadlinesWidget />
        </div>
        <div className="space-y-4">
          <OverdueClientsWidget />
          <RecentReconciliationsWidget />
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat(compliance): Dashboard renders three Phase D widgets"
```

---

## Task D10: ClientCalendarTab

**Files:**
- Create: `frontend/src/components/compliance/ClientCalendarTab.tsx`

- [ ] **Step 1: Write the tab**

```tsx
// frontend/src/components/compliance/ClientCalendarTab.tsx
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
```

- [ ] **Step 2: Verify TypeScript**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/compliance/ClientCalendarTab.tsx
git commit -m "feat(compliance): ClientCalendarTab with filter + inline status"
```

---

## Task D11: Wire ClientCalendarTab into ClientDetail

**Files:**
- Modify: `frontend/src/pages/ClientDetail.tsx`

- [ ] **Step 1: Replace the placeholder section**

Open `frontend/src/pages/ClientDetail.tsx`. Add the import near the existing imports:

```tsx
import { ClientCalendarTab } from "@/components/compliance/ClientCalendarTab"
```

Then replace the existing block:

```tsx
      <ClientReconciliationsList clientId={client.id} />

      <div className="border-t pt-6">
        <h2 className="text-lg font-semibold text-slate-900">Coming in later phases</h2>
        <p className="text-sm text-slate-600 mt-1">
          Documents (Phase C), Compliance Calendar (Phase D) — these tabs will appear here
          once their phases ship.
        </p>
      </div>
```

with:

```tsx
      <ClientReconciliationsList clientId={client.id} />

      <ClientCalendarTab clientId={client.id} />

      <div className="border-t pt-6">
        <h2 className="text-lg font-semibold text-slate-900">Coming in later phases</h2>
        <p className="text-sm text-slate-600 mt-1">
          Documents tab (file uploads beyond reconciliation) ships in a later phase.
        </p>
      </div>
```

- [ ] **Step 2: Verify TypeScript**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ClientDetail.tsx
git commit -m "feat(compliance): mount ClientCalendarTab on client detail"
```

---

## Task D12: Empty-state pass on Clients list

**Files:**
- Modify: `frontend/src/pages/Clients.tsx`

- [ ] **Step 1: Inspect current empty state**

Open `frontend/src/pages/Clients.tsx`. Look for the empty-state branch (where the table or list renders when `clients.length === 0`).

If the existing copy is friendly and points users to "Add client", leave it alone — note that in the commit message and skip step 2.

If it's terse (e.g. "No clients") or missing, replace with:

```tsx
<div className="rounded-md border border-dashed p-8 text-center">
  <p className="text-sm text-slate-700">No clients yet.</p>
  <p className="mt-1 text-xs text-slate-500">
    Add your first client to start tracking compliance deadlines and running reconciliations.
  </p>
</div>
```

(Use the existing "Add client" button above as the CTA — don't duplicate the button inside the empty card.)

- [ ] **Step 2: Verify TypeScript + run frontend tests**

Run: `cd frontend && npx tsc --noEmit && npm test`
Expected: TypeScript exit 0, all Vitest suites pass.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Clients.tsx
git commit -m "polish(clients): empty-state copy on Clients list"
```

If no changes were needed, skip the commit.

---

## Task D13: Build verification

- [ ] **Step 1: Type-check whole frontend**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 2: Run all frontend tests**

Run: `cd frontend && npm test`
Expected: all suites pass (the existing client-types tests + the two new helper test files).

- [ ] **Step 3: Production build**

Run: `cd frontend && npm run build`
Expected: build succeeds; only the existing chunk-size warning is emitted.

- [ ] **Step 4: Run all backend tests (no regressions expected)**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -q`
Expected: 59 passed.

If any step fails, fix the offender and re-run before continuing.

---

## Task D14: Manual acceptance test (matches the spec)

These steps verify the spec's acceptance criteria. Run them on a local dev environment (backend on :8000, frontend on :5173).

- [ ] **Step 1: Start servers**

In two terminals:

```bash
cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
```

- [ ] **Step 2: Sign up a fresh tenant**

Open `http://localhost:5173/signup` (or use the existing test user `tazwarjahin@gmail.com / TestRecon123!`). Complete `/onboard` if needed.

- [ ] **Step 3: Verify empty Dashboard**

Navigate to `/dashboard`. All three widgets render their empty-state copy (no errors in the console).

- [ ] **Step 4: Add 5 clients with mixed entity types**

Use the Clients page → Add client. Suggested mix:
1. Company, VAT-registered, fiscal year end 06-30
2. Company, not VAT-registered, fiscal year end 06-30
3. Partnership, VAT-registered
4. Individual
5. NGO

Each client creation calls `generate_compliance_events` (already wired in `useCreateClient`).

- [ ] **Step 5: Verify Dashboard populates**

Return to `/dashboard`. The Upcoming widget shows events for the next 30 days. The Overdue widget shows zero (all newly generated events have due dates ≥ today). Recent reconciliations remains empty unless a recon was run.

- [ ] **Step 6: Verify Calendar tab on a client**

Open one of the new clients. The Compliance calendar section shows every event for that client, default-sorted by due date. Filter buttons render and switch the table contents.

- [ ] **Step 7: Mark a row as Filed**

Pick the upcoming VAT return on a VAT-registered company. Use the inline status select → Filed. Toast confirms. Refresh the page — row remains Filed.

- [ ] **Step 8: Verify audit_log entry**

In the Supabase SQL editor or via the admin client, query:

```sql
select * from audit_log
where table_name = 'compliance_events'
order by created_at desc
limit 5;
```

Expect a row with `operation = 'UPDATE'`, the user_id of the test user, and the changed columns.

- [ ] **Step 9: Verify dashboard reflects the change**

Return to `/dashboard`. The upcoming widget no longer shows the just-filed row at the top with the pending badge — it either shows it as Filed (if still in the next 30 days) or has dropped it (if filtered out by your widget logic).

- [ ] **Step 10: Document results in the PR / commit message**

If any step fails, log what failed and fix before tagging Phase D complete.

---

## Task D15: Tag phase-d-complete

- [ ] **Step 1: Verify clean working tree**

Run: `git status`
Expected: nothing to commit.

- [ ] **Step 2: Tag**

```bash
git tag phase-d-complete -m "Phase D complete — Calendar + Dashboard

Frontend-only phase surfacing the existing compliance_events data:
- Dashboard with Upcoming / Overdue / Recent recons widgets
- Calendar tab on client detail (filterable table, inline status select)
- Empty-state pass on Dashboard widgets, calendar tab, clients list
- Two new pure helpers (groupByWeek, isOverdue) with unit tests

No backend changes, no migrations. The audit trigger captures status
flips automatically through PostgREST's JWT-claim handoff (verified in
the Phase A spike).

Acceptance test (5 mixed-entity clients, mark VAT return as filed,
audit_log entry, dashboard reflects change) passes."
```

- [ ] **Step 3: Confirm tag**

```bash
git tag -l | grep phase
```

Expected: `phase-a-complete`, `phase-b-complete`, `phase-c-complete`, `phase-d-complete`.

---

## Self-review checklist (for the writer)

- ✅ All spec sections covered: hooks (D2), badge/select (D3-D4), widgets (D6-D8), Dashboard rewrite (D9), Calendar tab (D10-D11), helper unit tests (D5), empty-state pass (D6, D7, D8, D10, D12), build verification (D13), acceptance test (D14), tag (D15).
- ✅ No "TBD" or "implement later" placeholders.
- ✅ Type names consistent across tasks: `ComplianceEventRow`, `ComplianceEventWithClient`, `OverdueByClient`, `EventStatus`, `SELECTABLE_STATUSES`.
- ✅ Hook names consistent: `useUpcomingEvents`, `useClientEvents`, `useOverdueByClient`, `useRecentReconciliations`, `useUpdateEventStatus`.
- ✅ Helper signatures match between definition (D5) and call sites (D6, D10).
