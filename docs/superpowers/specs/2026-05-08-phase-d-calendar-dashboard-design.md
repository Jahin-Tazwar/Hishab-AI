# Phase D — Calendar + Dashboard

**Date:** 2026-05-08
**Status:** Approved (pending user review of this spec)
**Predecessors:** `phase-a-complete`, `phase-b-complete`, `phase-c-complete`

## 1. One-line description

Make the existing compliance-events data usable: a Dashboard that surfaces what's coming up and what's overdue across all clients, a Calendar tab on each client showing every deadline with inline status updates, and an empty-states pass so the app feels finished on a fresh tenant.

## 2. Why this scope

Phase A seeded `bd_obligation_definitions` and built the `generate_compliance_events` RPC. Phase B wired client creation to call that RPC. So the compliance-events table is already populated correctly for every client in the system — but there is no UI surfacing it. The Dashboard is a placeholder, and the Calendar tab on `/clients/:id` is a "Coming in later phases" stub. Phase D closes that loop without changing the schema or adding a single backend route.

## 3. Architectural choices

### 3.1 Reads via Supabase, writes via Supabase

Same pattern as Phase B clients and the Phase C line-item override:

- TanStack Query → `supabase.from("compliance_events").select(...)`. RLS scopes to tenant.
- Status flips are a single-column update: `supabase.from("compliance_events").update({ status, filed_date }).eq("id", ...)`. The audit trigger captures the user automatically because PostgREST sets `request.jwt.claim.sub` within the request transaction.

We considered routing status updates through FastAPI for symmetry with the reconciliation flow. We rejected it: the only thing FastAPI would add is hops and code; the audit log already captures user identity correctly on direct Supabase writes (verified by the Phase A spike).

### 3.2 Overdue is derived, not stored

The `compliance_events.status` enum includes `'overdue'`, but Phase D never writes that value. Instead, queries that need "overdue" treat any row where `status = 'pending' AND due_date < today` as overdue.

This avoids needing a cron/scheduler to re-compute `overdue` rows nightly. The enum value stays in the schema for a future server-side workflow that might want to materialize it (e.g., snapshotting at month-end), but Phase D doesn't.

### 3.3 Calendar is a table, not a grid

Per the master MVP spec ("Calendar tab on client detail (table view, filter by status)"). A monthly calendar grid is a possible future enhancement; nothing about Phase D blocks adding one later.

## 4. Data shape (no schema changes)

`compliance_events` already has everything we need:

| Field             | Used by Phase D for                                          |
|-------------------|--------------------------------------------------------------|
| `id`              | Update target                                                |
| `client_id`       | Joins to clients for client name on Dashboard                |
| `obligation_type` | Renders display name via `bd_obligation_definitions` lookup  |
| `period_start/end`| Period column on calendar table                              |
| `due_date`        | Sorting + week grouping + overdue derivation                 |
| `status`          | Inline select; filter on calendar tab                        |
| `filed_date`      | Auto-set when status → filed; cleared when reverted          |
| `notes`           | Free-form note on the row (Phase D adds a small inline UI)  |
| `updated_at`      | Trigger updates this; used for "recently filed" if needed    |

The 6 seeded obligation types are: `vat_return`, `tds_return`, `tds_deposit`, `income_tax_company`, `income_tax_individual`, `rjsc_annual` (see `migrations/0008_seed_obligations.sql`).

## 5. Frontend components

### 5.1 New hooks (`src/hooks/useCompliance.ts`)

- `useUpcomingEvents(daysAhead = 30)` — events with `due_date BETWEEN today AND today + daysAhead`, joined to clients on `client_id`, ordered by `due_date`. Returns rows enriched with `client_name`. Empty if no clients.
- `useClientEvents(clientId, status?)` — all events for one client, optional status filter, newest due-date first within filter. Used by the calendar tab.
- `useOverdueByClient()` — `select count, client_id, clients.name from compliance_events where status='pending' and due_date<today group by client_id`. Renders the Overdue widget.
- `useRecentReconciliations(limit = 5)` — new; analogous to the existing `useClientReconciliations` but unscoped (returns the most-recent reconciliations across every client in the tenant). Joined to clients on `client_id` for the client name.
- `useUpdateEventStatus()` — mutation `{ id, status, filed_date?, notes? }`; invalidates upcoming, by-client, and overdue keys; optimistic update is intentionally not added (single-column flip; UX is fine without it).

Query keys live in a `complianceKeys` namespace mirroring `clientKeys` / `reconKeys`.

### 5.2 New components (`src/components/compliance/`)

- `EventStatusBadge.tsx` — five-state colour pill: `pending` (slate), `filed` (green), `overdue` (red — derived, not stored), `waived` (slate-light), `na` (slate-light, italic). Uses the same badge wrapper as `MatchStatusBadge`.
- `EventStatusSelect.tsx` — inline shadcn `<Select>` rendered in each calendar row's status cell. Options: Pending / Filed / Waived / N/A. Choosing **Filed** sets `filed_date = today`; choosing anything else clears `filed_date`. On change → `useUpdateEventStatus` mutation → toast on success/error. Disabled while saving.
- `UpcomingDeadlinesWidget.tsx` — Dashboard card. Reads `useUpcomingEvents(30)`, groups by week-from-today (This week / Next week / Weeks 3–4), renders rows with client name, obligation display name, due date, days-until. Empty-state copy: "No deadlines in the next 30 days. Add a client to populate the calendar."
- `OverdueClientsWidget.tsx` — Dashboard card. Reads `useOverdueByClient`, sorts desc by count, renders rows linking to that client. Empty-state copy: "No overdue items. 🎉"
- `RecentReconciliationsWidget.tsx` — Dashboard card. Reads `useRecentReconciliations(5)`. Each row: client name, period, at-risk ITC, link to the report. Empty-state copy: "No reconciliations yet."
- `ClientCalendarTab.tsx` — Renders inside `ClientDetail.tsx` in place of the current placeholder. A filterable table: filter buttons (All / Pending / Filed / Overdue / Waived / N/A), columns (Obligation, Period, Due, Status, Notes). Inline `EventStatusSelect` in the Status column. Notes column is a small in-place edit (textarea on click). Empty-state when filter yields zero rows + truly-empty (no events): friendly copy.

### 5.3 Pages touched

- `src/pages/Dashboard.tsx` — replace the placeholder card with a 3-card grid (Upcoming, Overdue, Recent recons).
- `src/pages/ClientDetail.tsx` — replace the "Coming in later phases" stub with `<ClientCalendarTab clientId={...}>`. Keep the section header.

### 5.4 Empty-state pass

Quick walk through:

- `Dashboard` widgets — already covered above
- `ClientCalendarTab` — covered
- `ClientReconciliationsList` (Phase C) — already has friendly copy, leave alone
- `Clients` list — review existing copy; if the "no clients yet" message is present and clean, leave alone, otherwise tighten

## 6. Helpers (with unit tests)

Two small pure helpers go in `src/lib/`:

- `groupByWeek(events, today)` — `(rows, today) → { thisWeek, nextWeek, weeksThreeAndFour }`. Tested for week-boundary cases (Sun start vs. Mon start: we use Mon start since BD work week is Sun–Thu but our users are CAs who think in Mon–Sun anyway).
- `isOverdue(event, today)` — single boolean for the EventStatusBadge.

Tests live in `src/lib/__tests__/groupByWeek.test.ts` and `isOverdue.test.ts` using the same Vitest setup the project already has.

## 7. Acceptance test (matches the master spec)

1. Sign up as a fresh tenant. Dashboard renders with three "no data yet" empty states. No errors.
2. Add 5 clients with mixed entity types (company/individual/partnership, mix of vat-registered vs not). Dashboard's upcoming widget populates with the next 30 days of generated events.
3. Open one client → Calendar tab shows every event for that client, default-sorted by due date.
4. Change one VAT return from Pending → Filed. Toast confirms; row updates; `audit_log` has a new entry attributed to the user; Dashboard's overdue count for that client (if it had one) decrements.
5. Filter to Filed → only the just-marked row remains.
6. Refresh — state persists.

## 8. Out of scope for Phase D

- Email / push deadline reminders
- Monthly calendar grid view (table works for the deliverables; grid is a future enhancement)
- Bulk-mark-as-filed
- Custom obligation types beyond the 6 seeded
- Cron job to materialise `status='overdue'` (we derive it; the enum value stays)

## 9. Risks

- **`useOverdueByClient` aggregation.** PostgREST supports group-by via `select=count(),client_id,clients(name)` syntax — this is the exact pattern Supabase docs cover. If we hit edge cases (RLS interaction with aggregates), fallback is fetching all pending+past rows and reducing on the client. Same data either way; just network volume.
- **Empty-state copy quality.** No automated way to test "feels finished." Acceptance test #1 is the only check; we'll review screenshots once the dashboard is wired.

## 10. File-level deliverable list

```
frontend/src/
  hooks/
    useCompliance.ts                                     [NEW]
  components/compliance/
    EventStatusBadge.tsx                                 [NEW]
    EventStatusSelect.tsx                                [NEW]
    UpcomingDeadlinesWidget.tsx                          [NEW]
    OverdueClientsWidget.tsx                             [NEW]
    RecentReconciliationsWidget.tsx                      [NEW]
    ClientCalendarTab.tsx                                [NEW]
  lib/
    groupByWeek.ts                                       [NEW]
    isOverdue.ts                                         [NEW]
    __tests__/
      groupByWeek.test.ts                                [NEW]
      isOverdue.test.ts                                  [NEW]
  pages/
    Dashboard.tsx                                        [REWRITE — three-widget grid]
    ClientDetail.tsx                                     [EDIT — replace stub with ClientCalendarTab]
```

No backend changes. No migrations. Done.
