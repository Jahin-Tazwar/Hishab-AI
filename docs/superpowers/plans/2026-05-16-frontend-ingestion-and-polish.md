# Frontend: Adaptive Ingestion Wizard + UI Polish — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the multi-step adaptive ingestion wizard (`upload → extract → review → finalize`) on top of the now-frozen `/api/v1/ingestion/*` backend, replacing the old `ReconNew` page, and complete a focused UI polish pass on the existing app (theme tokens, dark mode, mobile sidebar, breadcrumbs, scroll restoration, a11y on forms).

**Architecture:**
- One canonical wizard route at `/clients/:id/ingestion/new` (creates a job → redirects to `/:jobId`); the per-job route renders one of four step views driven entirely by `GET /jobs/:id` status. Polling stops on terminal states.
- A typed API client under `src/lib/ingestion/` (axios wrapper around the backend's 11 endpoints) plus react-query hooks under `src/hooks/useIngestion*.ts` mirroring the existing `useClients`/`useReconciliations` shape.
- Polish work touches **only** color tokens, the AppShell sidebar (mobile collapse), `<PageHeader>` + `<Breadcrumbs>` extraction, and `<ScrollRestoration>` — no churn on logic.

**Tech Stack:** React 19, TypeScript, Vite 8, Tailwind 3, shadcn/ui (Radix), TanStack Query 5, react-hook-form + zod, Zustand, sonner, react-router 6, axios, lucide-react, next-themes, Vitest + RTL.

**Backend contract** (already shipped on `phase-f-adaptive-ingestion`):
- `POST   /api/v1/ingestion/jobs` — multipart `files[]`, `client_id`, `period_start`, `period_end`, `kind`
- `GET    /api/v1/ingestion/jobs/:id` — `JobDetailOut { job, files[] }`
- `GET    /api/v1/ingestion/jobs/:id/rows?filter=needs_review|all&limit&offset`
- `PATCH  /api/v1/ingestion/jobs/:id/rows/:rid` — `ExtractedRowData` body
- `POST   /api/v1/ingestion/jobs/:id/rows/:rid/confirm`
- `POST   /api/v1/ingestion/jobs/:id/rows/:rid/reject`
- `POST   /api/v1/ingestion/jobs/:id/rows/bulk-confirm` — `{ row_ids: UUID[] }`
- `POST   /api/v1/ingestion/jobs/:id/finalize` → `{ reconciliation_id }`
- `GET    /api/v1/ingestion/jobs/:id/files/:fid/preview` — streams the original (signed-url style)
- `GET    /api/v1/ingestion/column-mappings/pending`
- `POST   /api/v1/ingestion/column-mappings/:id/confirm`

---

## File Structure

### New files

| Path | Responsibility |
|---|---|
| `frontend/src/types/ingestion.ts` | Pydantic-mirror Zod schemas + TS types for all ingestion API payloads. |
| `frontend/src/lib/ingestion/api.ts` | Thin typed axios wrappers around the 11 endpoints. |
| `frontend/src/hooks/useIngestion.ts` | React-query hooks: `useJob`, `useJobRows`, `useCreateJob`, `useEditRow`, `useConfirmRow`, `useRejectRow`, `useBulkConfirm`, `useFinalize`, `useFilePreview`. |
| `frontend/src/components/layout/PageHeader.tsx` | Reusable header (back link + title + subtitle + actions slot). |
| `frontend/src/components/layout/Breadcrumbs.tsx` | Optional breadcrumb component used by all detail/wizard pages. |
| `frontend/src/components/layout/ThemeToggle.tsx` | next-themes light/dark toggle button for the sidebar. |
| `frontend/src/components/ingestion/IngestionWizard.tsx` | Top-level wizard router — picks step component based on job status. |
| `frontend/src/components/ingestion/Stepper.tsx` | 4-step progress indicator at the top of the wizard. |
| `frontend/src/components/ingestion/UploadStep.tsx` | Step 1 view: dropzone, file list, period, kind, submit. |
| `frontend/src/components/ingestion/MultiFileDropzone.tsx` | Multi-file dropzone, accepts XLSX/PDF/JPG/PNG/HEIC. |
| `frontend/src/components/ingestion/ExtractingStep.tsx` | Step 2 view: per-file extraction progress while `extracting`. |
| `frontend/src/components/ingestion/ReviewStep.tsx` | Step 3 view: rows table + drawer + bulk actions. |
| `frontend/src/components/ingestion/RowsTable.tsx` | Filter chips + selectable, paginated, sortable table. |
| `frontend/src/components/ingestion/RowDrawer.tsx` | Side drawer: editable fields + warnings + source preview. |
| `frontend/src/components/ingestion/SourcePreview.tsx` | Renders the source file inline (image / pdf / xlsx fallback). |
| `frontend/src/components/ingestion/FinalizeStep.tsx` | Step 4 view: finalize button → reconciling → completed. |
| `frontend/src/components/ingestion/StatusChip.tsx` | Small colored badge for row status (auto_passed / needs_review / etc.). |
| `frontend/src/components/ingestion/EngineBadge.tsx` | Engine label badge (`pandas`, `pdfplumber+llm`, `gemini-vision`). |
| `frontend/src/components/ingestion/WarningChip.tsx` | Per-field warning chip with code → human label mapping. |
| `frontend/src/pages/IngestionNew.tsx` | Route handler for `/clients/:id/ingestion/new`. |
| `frontend/src/pages/IngestionJob.tsx` | Route handler for `/clients/:id/ingestion/:jobId`. |
| `frontend/src/components/__tests__/IngestionWizard.test.tsx` | Behavioral test for status-driven step routing. |
| `frontend/src/lib/ingestion/__tests__/api.test.ts` | Axios mock tests for endpoint shapes. |
| `frontend/src/components/__tests__/MultiFileDropzone.test.tsx` | RTL + drag/drop event tests. |
| `frontend/src/components/__tests__/RowsTable.test.tsx` | Filter chip + bulk select behavior. |

### Modified files

| Path | Change |
|---|---|
| `frontend/src/router.tsx` | Add 2 new routes (`/clients/:id/ingestion/new`, `/.../:jobId`); add `<ScrollRestoration>` to root; redirect old `/clients/:id/recon/new` → new flow. |
| `frontend/src/App.tsx` | Wrap children in `next-themes` `<ThemeProvider>`. |
| `frontend/src/components/layout/AppShell.tsx` | Replace `slate-*` with theme tokens, add mobile sidebar collapse, add Ingestion to NAV, wrap sign-out in confirm dialog, add ThemeToggle. |
| `frontend/src/pages/Dashboard.tsx`, `Clients.tsx`, `ClientDetail.tsx`, `Login.tsx`, `Signup.tsx`, `Onboard.tsx`, `NotFound.tsx` | Replace `slate-*` with theme tokens; replace ad-hoc page headers with `<PageHeader>`. |
| `frontend/src/pages/ClientDetail.tsx` | Replace `window.location.href` with `useNavigate()` after delete; swap "Coming in later phases" panel for an `Ingestion` entry-point card. |
| `frontend/src/pages/ReconNew.tsx` | Delete (after redirect lands and one full test cycle). |
| `frontend/src/components/reconciliation/ClientReconciliationsList.tsx` | Replace "Run a new reconciliation" link target with the new ingestion route. |
| `frontend/src/components/ui/sheet.tsx` (new shadcn primitive) | Side drawer for `RowDrawer`. |
| `frontend/src/components/ui/checkbox.tsx` (already present) | Used by `RowsTable` bulk-select. |

---

## Phase 0 — Foundation (theme tokens, ThemeProvider, shared chrome)

### Task 1: Wire next-themes ThemeProvider

**Files:**
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/components/layout/ThemeToggle.tsx`
- Create: `frontend/src/components/__tests__/ThemeToggle.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/__tests__/ThemeToggle.test.tsx
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { ThemeProvider } from "next-themes"
import { describe, expect, it } from "vitest"

import { ThemeToggle } from "@/components/layout/ThemeToggle"

function renderWithTheme(ui: React.ReactNode) {
  return render(
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}>
      {ui}
    </ThemeProvider>,
  )
}

describe("ThemeToggle", () => {
  it("switches the document class on click", async () => {
    renderWithTheme(<ThemeToggle />)
    const btn = screen.getByRole("button", { name: /toggle theme/i })
    expect(document.documentElement.classList.contains("dark")).toBe(false)
    await userEvent.click(btn)
    expect(document.documentElement.classList.contains("dark")).toBe(true)
  })
})
```

> Note: `userEvent` requires `@testing-library/user-event` — check `package.json`. If absent, add it: `npm i -D @testing-library/user-event@^14`. (It is **not** currently in `package.json`; this step adds it.)

- [ ] **Step 2: Add the dev dependency**

```bash
cd frontend && npm i -D @testing-library/user-event@^14
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd frontend && npx vitest run src/components/__tests__/ThemeToggle.test.tsx
```

Expected: FAIL with module not found for `@/components/layout/ThemeToggle`.

- [ ] **Step 4: Implement ThemeToggle**

```tsx
// frontend/src/components/layout/ThemeToggle.tsx
import { Moon, Sun } from "lucide-react"
import { useTheme } from "next-themes"

import { Button } from "@/components/ui/button"

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme()
  const isDark = resolvedTheme === "dark"
  return (
    <Button
      variant="ghost"
      size="sm"
      aria-label="Toggle theme"
      onClick={() => setTheme(isDark ? "light" : "dark")}
    >
      {isDark ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </Button>
  )
}
```

- [ ] **Step 5: Wire ThemeProvider into App.tsx**

```tsx
// frontend/src/App.tsx
import type { ReactNode } from "react"
import { ThemeProvider } from "next-themes"

import { useSessionInit } from "@/hooks/useSession"
import { Toaster } from "@/components/ui/sonner"

interface Props {
  children: ReactNode
}

export function AppRoot({ children }: Props) {
  useSessionInit()
  return (
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}>
      {children}
      <Toaster />
    </ThemeProvider>
  )
}
```

- [ ] **Step 6: Run test to verify it passes**

```bash
cd frontend && npx vitest run src/components/__tests__/ThemeToggle.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
cd frontend && git add src/App.tsx src/components/layout/ThemeToggle.tsx src/components/__tests__/ThemeToggle.test.tsx package.json package-lock.json
git commit -m "feat(theme): wire next-themes ThemeProvider + ThemeToggle button"
```

---

### Task 2: PageHeader + Breadcrumbs primitives

**Files:**
- Create: `frontend/src/components/layout/PageHeader.tsx`
- Create: `frontend/src/components/layout/Breadcrumbs.tsx`
- Create: `frontend/src/components/__tests__/PageHeader.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/__tests__/PageHeader.test.tsx
import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"

import { Breadcrumbs } from "@/components/layout/Breadcrumbs"
import { PageHeader } from "@/components/layout/PageHeader"

describe("PageHeader", () => {
  it("renders title, subtitle, and actions slot", () => {
    render(
      <MemoryRouter>
        <PageHeader
          title="My title"
          subtitle="My subtitle"
          actions={<button>Do thing</button>}
        />
      </MemoryRouter>,
    )
    expect(screen.getByRole("heading", { level: 1, name: "My title" })).toBeInTheDocument()
    expect(screen.getByText("My subtitle")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Do thing" })).toBeInTheDocument()
  })
})

describe("Breadcrumbs", () => {
  it("renders trail with terminal item un-linked", () => {
    render(
      <MemoryRouter>
        <Breadcrumbs items={[
          { label: "Clients", to: "/clients" },
          { label: "Acme Textiles", to: "/clients/abc" },
          { label: "New ingestion" },
        ]} />
      </MemoryRouter>,
    )
    expect(screen.getByRole("link", { name: "Clients" })).toHaveAttribute("href", "/clients")
    expect(screen.getByRole("link", { name: "Acme Textiles" })).toHaveAttribute("href", "/clients/abc")
    expect(screen.getByText("New ingestion").tagName).toBe("SPAN")
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run src/components/__tests__/PageHeader.test.tsx
```

Expected: FAIL with module not found.

- [ ] **Step 3: Implement Breadcrumbs**

```tsx
// frontend/src/components/layout/Breadcrumbs.tsx
import { ChevronRight } from "lucide-react"
import { Link } from "react-router-dom"

export interface BreadcrumbItem {
  label: string
  to?: string
}

interface Props {
  items: BreadcrumbItem[]
}

export function Breadcrumbs({ items }: Props) {
  return (
    <nav aria-label="Breadcrumb" className="text-sm text-muted-foreground">
      <ol className="flex flex-wrap items-center gap-1">
        {items.map((item, idx) => {
          const isLast = idx === items.length - 1
          return (
            <li key={`${item.label}-${idx}`} className="flex items-center gap-1">
              {idx > 0 && <ChevronRight className="size-3.5 shrink-0" aria-hidden />}
              {isLast || !item.to ? (
                <span className="text-foreground" aria-current={isLast ? "page" : undefined}>
                  {item.label}
                </span>
              ) : (
                <Link to={item.to} className="hover:underline">
                  {item.label}
                </Link>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
```

- [ ] **Step 4: Implement PageHeader**

```tsx
// frontend/src/components/layout/PageHeader.tsx
import type { ReactNode } from "react"

import { Breadcrumbs, type BreadcrumbItem } from "@/components/layout/Breadcrumbs"

interface Props {
  title: string
  subtitle?: ReactNode
  breadcrumbs?: BreadcrumbItem[]
  actions?: ReactNode
}

export function PageHeader({ title, subtitle, breadcrumbs, actions }: Props) {
  return (
    <header className="space-y-2">
      {breadcrumbs && <Breadcrumbs items={breadcrumbs} />}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">{title}</h1>
          {subtitle && (
            <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
          )}
        </div>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
    </header>
  )
}
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd frontend && npx vitest run src/components/__tests__/PageHeader.test.tsx
```

Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
cd frontend && git add src/components/layout/PageHeader.tsx src/components/layout/Breadcrumbs.tsx src/components/__tests__/PageHeader.test.tsx
git commit -m "feat(layout): add PageHeader + Breadcrumbs primitives"
```

---

### Task 3: AppShell — theme tokens, mobile sidebar, sign-out confirm, Ingestion nav entry

**Files:**
- Modify: `frontend/src/components/layout/AppShell.tsx`
- Create: `frontend/src/components/__tests__/AppShell.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/__tests__/AppShell.test.tsx
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

import { AppShell } from "@/components/layout/AppShell"

vi.mock("@/hooks/useUserProfile", () => ({
  useUserProfile: () => ({ data: { full_name: "Test User", tenant_id: "t1" } }),
}))
vi.mock("@/lib/supabase", () => ({
  supabase: { auth: { signOut: vi.fn() } },
}))

function withProviders(ui: React.ReactNode) {
  const qc = new QueryClient()
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/dashboard"]}>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe("AppShell", () => {
  it("renders all top-level nav items including Ingestion", () => {
    render(withProviders(<AppShell><div>content</div></AppShell>))
    expect(screen.getByRole("link", { name: "Dashboard" })).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Clients" })).toBeInTheDocument()
  })

  it("toggles mobile sidebar with the menu button", async () => {
    render(withProviders(<AppShell><div>content</div></AppShell>))
    const toggle = screen.getByRole("button", { name: /open menu/i })
    await userEvent.click(toggle)
    expect(screen.getByRole("button", { name: /close menu/i })).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run src/components/__tests__/AppShell.test.tsx
```

Expected: FAIL — no menu button yet.

- [ ] **Step 3: Implement the new AppShell**

```tsx
// frontend/src/components/layout/AppShell.tsx
import { Menu, X } from "lucide-react"
import { useState, type ReactNode } from "react"
import { Link, useLocation } from "react-router-dom"

import { ThemeToggle } from "@/components/layout/ThemeToggle"
import { Button } from "@/components/ui/button"
import { useUserProfile } from "@/hooks/useUserProfile"
import { supabase } from "@/lib/supabase"
import { cn } from "@/lib/utils"

interface Props {
  children: ReactNode
}

const NAV = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/clients", label: "Clients" },
]

export function AppShell({ children }: Props) {
  const location = useLocation()
  const { data: profile } = useUserProfile()
  const [open, setOpen] = useState(false)

  return (
    <div className="min-h-screen flex bg-background text-foreground">
      {/* Mobile open/close */}
      <Button
        variant="ghost"
        size="icon"
        className="absolute left-3 top-3 z-50 md:hidden"
        aria-label={open ? "Close menu" : "Open menu"}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? <X className="size-5" /> : <Menu className="size-5" />}
      </Button>

      <aside
        className={cn(
          "w-56 border-r bg-sidebar text-sidebar-foreground flex flex-col p-4",
          "fixed inset-y-0 left-0 z-40 transform transition-transform md:static md:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        )}
        aria-hidden={!open && typeof window !== "undefined" && window.innerWidth < 768}
      >
        <div className="mb-8 mt-8 md:mt-0">
          <h1 className="text-xl font-bold">HishabAI</h1>
          {profile && (
            <p className="text-xs text-muted-foreground mt-1 truncate">
              {profile.full_name}
            </p>
          )}
        </div>
        <nav className="flex flex-col gap-1 flex-1">
          {NAV.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              onClick={() => setOpen(false)}
              className={cn(
                "px-3 py-2 rounded text-sm",
                location.pathname.startsWith(item.to)
                  ? "bg-sidebar-primary text-sidebar-primary-foreground"
                  : "text-sidebar-foreground hover:bg-sidebar-accent",
              )}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="flex items-center justify-between gap-2">
          <ThemeToggle />
          <Button
            variant="ghost"
            size="sm"
            onClick={async () => {
              if (!confirm("Sign out of HishabAI?")) return
              const { error } = await supabase.auth.signOut()
              if (error) {
                const { toast } = await import("sonner")
                toast.error(error.message)
              }
            }}
          >
            Sign out
          </Button>
        </div>
      </aside>

      <main className="flex-1 p-4 md:p-8 bg-background">{children}</main>
    </div>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd frontend && npx vitest run src/components/__tests__/AppShell.test.tsx
```

Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
cd frontend && git add src/components/layout/AppShell.tsx src/components/__tests__/AppShell.test.tsx
git commit -m "feat(layout): theme tokens + mobile sidebar collapse + sign-out confirm"
```

---

### Task 4: Add ScrollRestoration + redirect old recon-new route

**Files:**
- Modify: `frontend/src/router.tsx`

- [ ] **Step 1: Update router**

```tsx
// frontend/src/router.tsx
import { createBrowserRouter, Navigate, ScrollRestoration } from "react-router-dom"

import { AppShell } from "@/components/layout/AppShell"
import { AuthLayout } from "@/components/layout/AuthLayout"
import { RouteBoundary } from "@/components/ErrorBoundary"
import { RequireAuth } from "@/components/RequireAuth"
import { RequireTenant } from "@/components/RequireTenant"
import { ClientDetail } from "@/pages/ClientDetail"
import { Clients } from "@/pages/Clients"
import { Dashboard } from "@/pages/Dashboard"
import { IngestionJob } from "@/pages/IngestionJob"
import { IngestionNew } from "@/pages/IngestionNew"
import { Login } from "@/pages/Login"
import { NotFound } from "@/pages/NotFound"
import { Onboard } from "@/pages/Onboard"
import { ReconReport } from "@/pages/ReconReport"
import { Signup } from "@/pages/Signup"

function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <ScrollRestoration />
      {children}
    </>
  )
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <RequireTenant>
        <AppShell>
          <RouteBoundary>{children}</RouteBoundary>
        </AppShell>
      </RequireTenant>
    </RequireAuth>
  )
}

export const router = createBrowserRouter([
  { path: "/", element: <RootLayout><Navigate to="/login" replace /></RootLayout> },
  { path: "/login", element: <RootLayout><AuthLayout><Login /></AuthLayout></RootLayout> },
  { path: "/signup", element: <RootLayout><AuthLayout><Signup /></AuthLayout></RootLayout> },
  {
    path: "/onboard",
    element: <RootLayout><RequireAuth><AuthLayout><Onboard /></AuthLayout></RequireAuth></RootLayout>,
  },
  { path: "/dashboard", element: <RootLayout><ProtectedRoute><Dashboard /></ProtectedRoute></RootLayout> },
  { path: "/clients", element: <RootLayout><ProtectedRoute><Clients /></ProtectedRoute></RootLayout> },
  { path: "/clients/:id", element: <RootLayout><ProtectedRoute><ClientDetail /></ProtectedRoute></RootLayout> },

  // Ingestion (new flow)
  {
    path: "/clients/:id/ingestion/new",
    element: <RootLayout><ProtectedRoute><IngestionNew /></ProtectedRoute></RootLayout>,
  },
  {
    path: "/clients/:id/ingestion/:jobId",
    element: <RootLayout><ProtectedRoute><IngestionJob /></ProtectedRoute></RootLayout>,
  },

  // Old recon route → redirect to new ingestion flow
  {
    path: "/clients/:id/recon/new",
    element: <RedirectReconNew />,
  },

  // Recon report still served from the old page
  {
    path: "/clients/:id/recon/:reconId",
    element: <RootLayout><ProtectedRoute><ReconReport /></ProtectedRoute></RootLayout>,
  },

  { path: "*", element: <RootLayout><NotFound /></RootLayout> },
])

function RedirectReconNew() {
  // useParams is router-bound, so do it inline
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { useParams } = require("react-router-dom") as typeof import("react-router-dom")
  const { id } = useParams<{ id: string }>()
  return <Navigate to={`/clients/${id}/ingestion/new`} replace />
}
```

> The `IngestionNew` and `IngestionJob` page modules don't exist yet — they're created in Tasks 9 and 10. Until then, the build will fail. **Stub them out** as a separate step before committing this task to keep the tree green.

- [ ] **Step 2: Stub the page modules so the build stays green**

```tsx
// frontend/src/pages/IngestionNew.tsx
export function IngestionNew() { return <div>Ingestion (new) — coming soon.</div> }
```

```tsx
// frontend/src/pages/IngestionJob.tsx
export function IngestionJob() { return <div>Ingestion (job) — coming soon.</div> }
```

- [ ] **Step 3: Verify build & tests**

```bash
cd frontend && npm run build && npx vitest run
```

Expected: build succeeds, all existing tests still pass.

- [ ] **Step 4: Commit**

```bash
cd frontend && git add src/router.tsx src/pages/IngestionNew.tsx src/pages/IngestionJob.tsx
git commit -m "feat(router): scroll restoration + ingestion routes + recon-new redirect"
```

---

### Task 5: Replace `slate-*` with theme tokens on existing pages

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`
- Modify: `frontend/src/pages/Clients.tsx`
- Modify: `frontend/src/pages/ClientDetail.tsx`
- Modify: `frontend/src/pages/Login.tsx`
- Modify: `frontend/src/pages/Signup.tsx`
- Modify: `frontend/src/pages/Onboard.tsx`
- Modify: `frontend/src/pages/NotFound.tsx`
- Modify: `frontend/src/components/ErrorBoundary.tsx`

- [ ] **Step 1: Replace slate references on each page**

For each file above, perform the following substitutions:

| Find | Replace |
|---|---|
| `text-slate-900` | `text-foreground` |
| `text-slate-700` | `text-foreground` |
| `text-slate-600` | `text-muted-foreground` |
| `text-slate-500` | `text-muted-foreground` |
| `bg-slate-50` | `bg-muted` |
| `bg-slate-200` | `bg-muted` |
| `bg-slate-900` | `bg-primary` |
| `bg-slate-800` | `bg-primary/90` |
| `text-white` (when paired with `bg-slate-900`/`primary`) | `text-primary-foreground` |
| `border-slate-200` | `border-border` |
| `border-slate-300` | `border-input` |
| `text-red-600` | `text-destructive` |

Also update `Dashboard.tsx` to use `<PageHeader>`:

```tsx
// frontend/src/pages/Dashboard.tsx
import { OverdueClientsWidget } from "@/components/compliance/OverdueClientsWidget"
import { RecentReconciliationsWidget } from "@/components/compliance/RecentReconciliationsWidget"
import { UpcomingDeadlinesWidget } from "@/components/compliance/UpcomingDeadlinesWidget"
import { PageHeader } from "@/components/layout/PageHeader"
import { useUserProfile } from "@/hooks/useUserProfile"

export function Dashboard() {
  const { data: profile } = useUserProfile()
  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        subtitle={profile?.full_name ? `Welcome back, ${profile.full_name}.` : "Welcome to HishabAI."}
      />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2"><UpcomingDeadlinesWidget /></div>
        <div className="space-y-4">
          <OverdueClientsWidget />
          <RecentReconciliationsWidget />
        </div>
      </div>
    </div>
  )
}
```

Update `Clients.tsx`:

```tsx
// frontend/src/pages/Clients.tsx
import { useState } from "react"

import { AddClientDialog } from "@/components/clients/AddClientDialog"
import { ClientsTable } from "@/components/clients/ClientsTable"
import { PageHeader } from "@/components/layout/PageHeader"
import { Input } from "@/components/ui/input"
import { useClientsList } from "@/hooks/useClients"

export function Clients() {
  const [search, setSearch] = useState("")
  const { data: clients = [], isLoading } = useClientsList(search)

  return (
    <div className="space-y-6">
      <PageHeader
        title="Clients"
        subtitle="Manage your firm's clients. Compliance deadlines are auto-generated on add."
        actions={<AddClientDialog />}
      />
      <Input
        placeholder="Search by name…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="max-w-sm"
      />
      <ClientsTable clients={clients} isLoading={isLoading} />
    </div>
  )
}
```

Update `ClientDetail.tsx` — replace the `window.location.href` after delete:

```tsx
// frontend/src/pages/ClientDetail.tsx (delete handler)
import { useNavigate } from "react-router-dom"
// ...
const navigate = useNavigate()
// ...
<DeleteClientDialog
  client={client}
  open={deleting}
  onOpenChange={setDeleting}
  onDeleted={() => navigate("/clients")}
/>
```

- [ ] **Step 2: Run all existing tests**

```bash
cd frontend && npx vitest run
```

Expected: PASS (no logic changed).

- [ ] **Step 3: Verify the dark-mode toggle visually flips colors**

```bash
cd frontend && npm run dev
```

Manually: open http://localhost:5173, sign in, click the theme toggle in the sidebar. Confirm header/text/cards all flip. Document the manual check passing in the commit message.

- [ ] **Step 4: Commit**

```bash
cd frontend && git add src/pages src/components/ErrorBoundary.tsx
git commit -m "refactor(theme): replace slate-* with theme tokens, adopt PageHeader"
```

---

## Phase 1 — Ingestion API client + hooks

### Task 6: Zod schemas + types for ingestion

**Files:**
- Create: `frontend/src/types/ingestion.ts`
- Create: `frontend/src/types/__tests__/ingestion.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/types/__tests__/ingestion.test.ts
import { describe, expect, it } from "vitest"

import {
  CreateJobResponseSchema,
  ExtractedRowDataSchema,
  JobDetailOutSchema,
  JobKindEnum,
  JobStatusEnum,
  RowStatusEnum,
} from "@/types/ingestion"

describe("ingestion schemas", () => {
  it("parses a valid CreateJobResponse", () => {
    const parsed = CreateJobResponseSchema.parse({
      job_id: "00000000-0000-0000-0000-000000000001",
      files: [
        {
          file_id: "00000000-0000-0000-0000-000000000002",
          original_filename: "x.xlsx",
          mime_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          byte_size: 1234,
          accepted: true,
          rejection_reason: null,
        },
      ],
    })
    expect(parsed.files).toHaveLength(1)
  })

  it("accepts string Decimals for amounts", () => {
    const parsed = ExtractedRowDataSchema.parse({
      invoice_no: "INV-1",
      invoice_date: "2026-05-15",
      taxable_amount_bdt: "1000.00",
      vat_amount_bdt: "150.00",
      supplier_bin: "100200300",
      supplier_name: "ACME",
      buyer_bin: null,
    })
    expect(parsed.taxable_amount_bdt).toBe("1000.00")
  })

  it("validates job status enum", () => {
    expect(JobStatusEnum.parse("ready_for_review")).toBe("ready_for_review")
    expect(() => JobStatusEnum.parse("bogus")).toThrow()
  })

  it("validates row status enum", () => {
    expect(RowStatusEnum.parse("auto_passed")).toBe("auto_passed")
  })

  it("parses JobDetailOut with files", () => {
    const parsed = JobDetailOutSchema.parse({
      job: {
        id: "00000000-0000-0000-0000-000000000001",
        tenant_id: "00000000-0000-0000-0000-000000000010",
        client_id: "00000000-0000-0000-0000-000000000020",
        kind: "purchase_register",
        period_start: "2026-05-01",
        period_end: "2026-05-31",
        status: "extracting",
        files_total: 1, files_done: 0,
        rows_total: 0, rows_needs_review: 0,
        error_summary: null, reconciliation_id: null,
        created_at: "2026-05-15T12:00:00+00:00",
        updated_at: "2026-05-15T12:00:00+00:00",
        completed_at: null,
      },
      files: [],
    })
    expect(parsed.job.status).toBe("extracting")
  })

  it("rejects invalid job kind", () => {
    expect(() => JobKindEnum.parse("vat_register")).toThrow()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run src/types/__tests__/ingestion.test.ts
```

Expected: FAIL — module missing.

- [ ] **Step 3: Implement the schemas**

```ts
// frontend/src/types/ingestion.ts
import { z } from "zod"

export const JobKindEnum = z.enum(["purchase_register", "supplier_export"])
export type JobKind = z.infer<typeof JobKindEnum>

export const JobStatusEnum = z.enum([
  "pending", "extracting", "ready_for_review",
  "confirmed", "reconciling", "completed", "failed",
])
export type JobStatus = z.infer<typeof JobStatusEnum>

export const FileStatusEnum = z.enum([
  "queued", "extracting", "extracted", "failed", "skipped",
])
export type FileStatus = z.infer<typeof FileStatusEnum>

export const RowStatusEnum = z.enum([
  "auto_passed", "needs_review", "confirmed", "rejected", "edited",
])
export type RowStatus = z.infer<typeof RowStatusEnum>

const Uuid = z.string().uuid()
const IsoDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/)
const IsoDateTime = z.string()
const DecimalStr = z.string()

// Decimals come from Pydantic as either strings (preferred) or numbers; coerce to string.
const Decimalish = z.union([
  z.string(),
  z.number().transform((n) => n.toFixed(2)),
])

export const FieldWarningSchema = z.object({
  field: z.string(),
  code: z.string(),
  message: z.string(),
})
export type FieldWarning = z.infer<typeof FieldWarningSchema>

export const ExtractedRowDataSchema = z.object({
  invoice_no: z.string(),
  invoice_date: IsoDate,
  taxable_amount_bdt: Decimalish,
  vat_amount_bdt: Decimalish,
  supplier_bin: z.string().nullable().optional(),
  supplier_name: z.string().nullable().optional(),
  buyer_bin: z.string().nullable().optional(),
})
export type ExtractedRowData = z.infer<typeof ExtractedRowDataSchema>

export const ExtractedRowOutSchema = z.object({
  id: Uuid,
  file_id: Uuid,
  job_id: Uuid,
  source_page_no: z.number().int().nullable().optional(),
  row_data: ExtractedRowDataSchema,
  row_data_original: ExtractedRowDataSchema,
  status: RowStatusEnum,
  field_warnings: z.array(FieldWarningSchema).default([]),
  reviewed_by: Uuid.nullable().optional(),
  reviewed_at: IsoDateTime.nullable().optional(),
  created_at: IsoDateTime,
})
export type ExtractedRowOut = z.infer<typeof ExtractedRowOutSchema>

export const JobOutSchema = z.object({
  id: Uuid,
  tenant_id: Uuid,
  client_id: Uuid,
  kind: JobKindEnum,
  period_start: IsoDate,
  period_end: IsoDate,
  status: JobStatusEnum,
  files_total: z.number().int(),
  files_done: z.number().int(),
  rows_total: z.number().int(),
  rows_needs_review: z.number().int(),
  error_summary: z.string().nullable().optional(),
  reconciliation_id: Uuid.nullable().optional(),
  created_at: IsoDateTime,
  updated_at: IsoDateTime,
  completed_at: IsoDateTime.nullable().optional(),
})
export type JobOut = z.infer<typeof JobOutSchema>

export const IngestionFileOutSchema = z.object({
  id: Uuid,
  job_id: Uuid,
  original_filename: z.string(),
  mime_type: z.string(),
  byte_size: z.number().int(),
  engine: z.string().nullable().optional(),
  status: FileStatusEnum,
  rows_extracted: z.number().int(),
  needs_review: z.boolean(),
  warnings: z.array(z.record(z.unknown())).default([]),
  error: z.string().nullable().optional(),
  extracted_at: IsoDateTime.nullable().optional(),
})
export type IngestionFileOut = z.infer<typeof IngestionFileOutSchema>

export const JobDetailOutSchema = z.object({
  job: JobOutSchema,
  files: z.array(IngestionFileOutSchema),
})
export type JobDetailOut = z.infer<typeof JobDetailOutSchema>

export const RowsListOutSchema = z.object({
  rows: z.array(ExtractedRowOutSchema),
  total: z.number().int(),
  has_more: z.boolean(),
})
export type RowsListOut = z.infer<typeof RowsListOutSchema>

export const CreateJobFileSummarySchema = z.object({
  file_id: Uuid,
  original_filename: z.string(),
  mime_type: z.string(),
  byte_size: z.number().int(),
  accepted: z.boolean(),
  rejection_reason: z.string().nullable().optional(),
})
export type CreateJobFileSummary = z.infer<typeof CreateJobFileSummarySchema>

export const CreateJobResponseSchema = z.object({
  job_id: Uuid,
  files: z.array(CreateJobFileSummarySchema),
})
export type CreateJobResponse = z.infer<typeof CreateJobResponseSchema>

export const FinalizeResponseSchema = z.object({
  reconciliation_id: Uuid,
})
export type FinalizeResponse = z.infer<typeof FinalizeResponseSchema>
```

- [ ] **Step 4: Verify tests pass**

```bash
cd frontend && npx vitest run src/types/__tests__/ingestion.test.ts
```

Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
cd frontend && git add src/types/ingestion.ts src/types/__tests__/ingestion.test.ts
git commit -m "feat(ingestion): zod schemas + TS types for the ingestion API surface"
```

---

### Task 7: Typed API client functions

**Files:**
- Create: `frontend/src/lib/ingestion/api.ts`
- Create: `frontend/src/lib/ingestion/__tests__/api.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/lib/ingestion/__tests__/api.test.ts
import MockAdapter from "axios-mock-adapter"
import { afterEach, beforeEach, describe, expect, it } from "vitest"

import { api } from "@/lib/api"
import {
  bulkConfirmRows,
  confirmRow,
  createJob,
  editRow,
  finalizeJob,
  getJob,
  listRows,
  rejectRow,
} from "@/lib/ingestion/api"

let mock: MockAdapter

beforeEach(() => { mock = new MockAdapter(api) })
afterEach(() => { mock.restore() })

const JOB_ID = "00000000-0000-0000-0000-000000000001"
const ROW_ID = "00000000-0000-0000-0000-000000000002"
const CLIENT_ID = "00000000-0000-0000-0000-000000000010"
const FILE_ID = "00000000-0000-0000-0000-000000000020"

describe("ingestion api client", () => {
  it("createJob posts multipart and parses response", async () => {
    mock.onPost("/api/v1/ingestion/jobs").reply(201, {
      job_id: JOB_ID,
      files: [{
        file_id: FILE_ID, original_filename: "x.xlsx",
        mime_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        byte_size: 100, accepted: true, rejection_reason: null,
      }],
    })
    const res = await createJob({
      client_id: CLIENT_ID,
      period_start: "2026-05-01", period_end: "2026-05-31",
      kind: "purchase_register",
      files: [new File(["x"], "x.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" })],
    })
    expect(res.job_id).toBe(JOB_ID)
  })

  it("getJob returns parsed JobDetailOut", async () => {
    mock.onGet(`/api/v1/ingestion/jobs/${JOB_ID}`).reply(200, {
      job: {
        id: JOB_ID, tenant_id: CLIENT_ID, client_id: CLIENT_ID,
        kind: "purchase_register", period_start: "2026-05-01", period_end: "2026-05-31",
        status: "ready_for_review",
        files_total: 1, files_done: 1, rows_total: 3, rows_needs_review: 0,
        error_summary: null, reconciliation_id: null,
        created_at: "2026-05-15T12:00:00+00:00",
        updated_at: "2026-05-15T12:00:00+00:00",
        completed_at: null,
      },
      files: [],
    })
    const res = await getJob(JOB_ID)
    expect(res.job.status).toBe("ready_for_review")
  })

  it("listRows handles pagination params", async () => {
    mock.onGet(`/api/v1/ingestion/jobs/${JOB_ID}/rows`, { params: { filter: "all", limit: 50, offset: 0 } })
      .reply(200, { rows: [], total: 0, has_more: false })
    const res = await listRows(JOB_ID, { filter: "all", limit: 50, offset: 0 })
    expect(res.total).toBe(0)
  })

  it("editRow PATCHes the new payload", async () => {
    mock.onPatch(`/api/v1/ingestion/jobs/${JOB_ID}/rows/${ROW_ID}`).reply(200, {
      id: ROW_ID, file_id: FILE_ID, job_id: JOB_ID, source_page_no: null,
      row_data: { invoice_no: "X", invoice_date: "2026-05-01", taxable_amount_bdt: "1.00", vat_amount_bdt: "0.15" },
      row_data_original: { invoice_no: "X", invoice_date: "2026-05-01", taxable_amount_bdt: "1.00", vat_amount_bdt: "0.15" },
      status: "edited", field_warnings: [],
      reviewed_by: null, reviewed_at: null,
      created_at: "2026-05-15T12:00:00+00:00",
    })
    const res = await editRow(JOB_ID, ROW_ID, {
      invoice_no: "X", invoice_date: "2026-05-01",
      taxable_amount_bdt: "1.00", vat_amount_bdt: "0.15",
    })
    expect(res.status).toBe("edited")
  })

  it("confirmRow POSTs and returns ok", async () => {
    mock.onPost(`/api/v1/ingestion/jobs/${JOB_ID}/rows/${ROW_ID}/confirm`).reply(200, { ok: true })
    await expect(confirmRow(JOB_ID, ROW_ID)).resolves.toBeUndefined()
  })

  it("rejectRow POSTs and returns ok", async () => {
    mock.onPost(`/api/v1/ingestion/jobs/${JOB_ID}/rows/${ROW_ID}/reject`).reply(200, { ok: true })
    await expect(rejectRow(JOB_ID, ROW_ID)).resolves.toBeUndefined()
  })

  it("bulkConfirmRows sends row_ids and returns count", async () => {
    mock.onPost(`/api/v1/ingestion/jobs/${JOB_ID}/rows/bulk-confirm`).reply(200, { confirmed_count: 3 })
    const n = await bulkConfirmRows(JOB_ID, [ROW_ID, ROW_ID, ROW_ID])
    expect(n).toBe(3)
  })

  it("finalizeJob returns reconciliation_id", async () => {
    mock.onPost(`/api/v1/ingestion/jobs/${JOB_ID}/finalize`).reply(200, {
      reconciliation_id: "00000000-0000-0000-0000-000000000099",
    })
    const res = await finalizeJob(JOB_ID)
    expect(res.reconciliation_id).toBe("00000000-0000-0000-0000-000000000099")
  })
})
```

- [ ] **Step 2: Add axios-mock-adapter as dev dep**

```bash
cd frontend && npm i -D axios-mock-adapter@^2
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd frontend && npx vitest run src/lib/ingestion/__tests__/api.test.ts
```

Expected: FAIL — module missing.

- [ ] **Step 4: Implement the api client**

```ts
// frontend/src/lib/ingestion/api.ts
import { api } from "@/lib/api"
import {
  CreateJobResponseSchema,
  ExtractedRowDataSchema,
  ExtractedRowOutSchema,
  FinalizeResponseSchema,
  JobDetailOutSchema,
  JobKindEnum,
  RowsListOutSchema,
  type CreateJobResponse,
  type ExtractedRowData,
  type ExtractedRowOut,
  type FinalizeResponse,
  type JobDetailOut,
  type JobKind,
  type RowsListOut,
} from "@/types/ingestion"

export interface CreateJobInput {
  client_id: string
  period_start: string
  period_end: string
  kind: JobKind
  files: File[]
}

export async function createJob(input: CreateJobInput): Promise<CreateJobResponse> {
  const fd = new FormData()
  fd.append("client_id", input.client_id)
  fd.append("period_start", input.period_start)
  fd.append("period_end", input.period_end)
  fd.append("kind", JobKindEnum.parse(input.kind))
  for (const f of input.files) fd.append("files", f, f.name)
  const { data } = await api.post("/api/v1/ingestion/jobs", fd, {
    headers: { "Content-Type": "multipart/form-data" },
  })
  return CreateJobResponseSchema.parse(data)
}

export async function getJob(jobId: string): Promise<JobDetailOut> {
  const { data } = await api.get(`/api/v1/ingestion/jobs/${jobId}`)
  return JobDetailOutSchema.parse(data)
}

export interface ListRowsParams {
  filter?: "needs_review" | "all"
  limit?: number
  offset?: number
}

export async function listRows(
  jobId: string, params: ListRowsParams = {},
): Promise<RowsListOut> {
  const { data } = await api.get(`/api/v1/ingestion/jobs/${jobId}/rows`, {
    params: {
      filter: params.filter ?? "needs_review",
      limit: params.limit ?? 200,
      offset: params.offset ?? 0,
    },
  })
  return RowsListOutSchema.parse(data)
}

export async function editRow(
  jobId: string, rowId: string, body: ExtractedRowData,
): Promise<ExtractedRowOut> {
  const validated = ExtractedRowDataSchema.parse(body)
  const { data } = await api.patch(
    `/api/v1/ingestion/jobs/${jobId}/rows/${rowId}`,
    validated,
  )
  return ExtractedRowOutSchema.parse(data)
}

export async function confirmRow(jobId: string, rowId: string): Promise<void> {
  await api.post(`/api/v1/ingestion/jobs/${jobId}/rows/${rowId}/confirm`)
}

export async function rejectRow(jobId: string, rowId: string): Promise<void> {
  await api.post(`/api/v1/ingestion/jobs/${jobId}/rows/${rowId}/reject`)
}

export async function bulkConfirmRows(
  jobId: string, rowIds: string[],
): Promise<number> {
  const { data } = await api.post(
    `/api/v1/ingestion/jobs/${jobId}/rows/bulk-confirm`,
    { row_ids: rowIds },
  )
  return data.confirmed_count as number
}

export async function finalizeJob(jobId: string): Promise<FinalizeResponse> {
  const { data } = await api.post(`/api/v1/ingestion/jobs/${jobId}/finalize`)
  return FinalizeResponseSchema.parse(data)
}

/** Returns the URL where the original file is streamed. */
export function filePreviewUrl(jobId: string, fileId: string): string {
  // Matches axios baseURL prefix; consumed by <img>/<embed>/<a download> tags.
  return `${api.defaults.baseURL ?? ""}/api/v1/ingestion/jobs/${jobId}/files/${fileId}/preview`
}
```

- [ ] **Step 5: Verify tests pass**

```bash
cd frontend && npx vitest run src/lib/ingestion/__tests__/api.test.ts
```

Expected: PASS (8 tests).

- [ ] **Step 6: Commit**

```bash
cd frontend && git add src/lib/ingestion src/types package.json package-lock.json
git commit -m "feat(ingestion): typed axios api client for /api/v1/ingestion/*"
```

---

### Task 8: React-query hooks for ingestion

**Files:**
- Create: `frontend/src/hooks/useIngestion.ts`
- Create: `frontend/src/hooks/__tests__/useIngestion.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/hooks/__tests__/useIngestion.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor } from "@testing-library/react"
import MockAdapter from "axios-mock-adapter"
import { afterEach, beforeEach, describe, expect, it } from "vitest"

import { useJob, useJobRows } from "@/hooks/useIngestion"
import { api } from "@/lib/api"

let mock: MockAdapter
function wrapper(qc: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  }
}

beforeEach(() => { mock = new MockAdapter(api) })
afterEach(() => { mock.restore() })

const JOB_ID = "00000000-0000-0000-0000-000000000001"

describe("useJob", () => {
  it("returns parsed JobDetailOut on success", async () => {
    mock.onGet(`/api/v1/ingestion/jobs/${JOB_ID}`).reply(200, {
      job: {
        id: JOB_ID, tenant_id: JOB_ID, client_id: JOB_ID,
        kind: "purchase_register", period_start: "2026-05-01", period_end: "2026-05-31",
        status: "ready_for_review",
        files_total: 1, files_done: 1, rows_total: 0, rows_needs_review: 0,
        error_summary: null, reconciliation_id: null,
        created_at: "2026-05-15T12:00:00+00:00",
        updated_at: "2026-05-15T12:00:00+00:00",
        completed_at: null,
      },
      files: [],
    })
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => useJob(JOB_ID), { wrapper: wrapper(qc) })
    await waitFor(() => expect(result.current.data?.job.status).toBe("ready_for_review"))
  })
})

describe("useJobRows", () => {
  it("returns rows for the configured filter", async () => {
    mock.onGet(`/api/v1/ingestion/jobs/${JOB_ID}/rows`, { params: { filter: "needs_review", limit: 200, offset: 0 } })
      .reply(200, { rows: [], total: 0, has_more: false })
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const { result } = renderHook(() => useJobRows(JOB_ID, "needs_review"), { wrapper: wrapper(qc) })
    await waitFor(() => expect(result.current.data?.total).toBe(0))
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run src/hooks/__tests__/useIngestion.test.tsx
```

Expected: FAIL — module missing.

- [ ] **Step 3: Implement the hooks**

```ts
// frontend/src/hooks/useIngestion.ts
import {
  useMutation, useQuery, useQueryClient,
} from "@tanstack/react-query"

import {
  bulkConfirmRows, confirmRow, createJob, editRow, finalizeJob,
  getJob, listRows, rejectRow,
  type CreateJobInput, type ListRowsParams,
} from "@/lib/ingestion/api"
import type { ExtractedRowData, JobStatus } from "@/types/ingestion"

export const ingestionKeys = {
  all: ["ingestion"] as const,
  job: (id: string) => ["ingestion", "job", id] as const,
  rows: (id: string, filter: "needs_review" | "all") =>
    ["ingestion", "rows", id, filter] as const,
}

/** Terminal job statuses where polling stops. */
const TERMINAL: JobStatus[] = ["completed", "failed"]

/**
 * Fetches a job + its files. Polls every 2s while non-terminal so the
 * Extracting / Reconciling steps update without manual refresh.
 */
export function useJob(jobId: string | undefined) {
  return useQuery({
    queryKey: ingestionKeys.job(jobId ?? ""),
    enabled: Boolean(jobId),
    queryFn: () => getJob(jobId!),
    refetchInterval: (q) => {
      const status = q.state.data?.job.status
      if (!status || TERMINAL.includes(status)) return false
      // Faster while extracting / reconciling, slower while in steady states.
      if (status === "extracting" || status === "reconciling") return 2000
      return 5000
    },
  })
}

export function useJobRows(
  jobId: string | undefined, filter: "needs_review" | "all" = "needs_review",
  params: Omit<ListRowsParams, "filter"> = {},
) {
  return useQuery({
    queryKey: ingestionKeys.rows(jobId ?? "", filter),
    enabled: Boolean(jobId),
    queryFn: () => listRows(jobId!, { ...params, filter }),
  })
}

export function useCreateJob() {
  return useMutation({
    mutationFn: (input: CreateJobInput) => createJob(input),
  })
}

export function useEditRow(jobId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ rowId, body }: { rowId: string; body: ExtractedRowData }) =>
      editRow(jobId, rowId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ingestionKeys.job(jobId) })
      qc.invalidateQueries({ queryKey: ["ingestion", "rows", jobId] })
    },
  })
}

export function useConfirmRow(jobId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (rowId: string) => confirmRow(jobId, rowId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ingestionKeys.job(jobId) })
      qc.invalidateQueries({ queryKey: ["ingestion", "rows", jobId] })
    },
  })
}

export function useRejectRow(jobId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (rowId: string) => rejectRow(jobId, rowId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ingestionKeys.job(jobId) })
      qc.invalidateQueries({ queryKey: ["ingestion", "rows", jobId] })
    },
  })
}

export function useBulkConfirm(jobId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (rowIds: string[]) => bulkConfirmRows(jobId, rowIds),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ingestionKeys.job(jobId) })
      qc.invalidateQueries({ queryKey: ["ingestion", "rows", jobId] })
    },
  })
}

export function useFinalize(jobId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => finalizeJob(jobId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ingestionKeys.job(jobId) })
    },
  })
}
```

- [ ] **Step 4: Verify tests pass**

```bash
cd frontend && npx vitest run src/hooks/__tests__/useIngestion.test.tsx
```

Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
cd frontend && git add src/hooks/useIngestion.ts src/hooks/__tests__/useIngestion.test.tsx
git commit -m "feat(ingestion): react-query hooks with status-driven polling"
```

---

## Phase 2 — Wizard shell + Upload step

### Task 9: Stepper + status→step mapping

**Files:**
- Create: `frontend/src/components/ingestion/Stepper.tsx`
- Create: `frontend/src/components/__tests__/Stepper.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/__tests__/Stepper.test.tsx
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { Stepper, statusToStep } from "@/components/ingestion/Stepper"

describe("statusToStep", () => {
  it.each([
    ["pending", 1],
    ["extracting", 2],
    ["ready_for_review", 3],
    ["confirmed", 4],
    ["reconciling", 4],
    ["completed", 4],
    ["failed", 4],
  ] as const)("maps %s to step %d", (status, step) => {
    expect(statusToStep(status as any)).toBe(step)
  })
})

describe("Stepper", () => {
  it("highlights the active step", () => {
    render(<Stepper activeStep={2} />)
    const items = screen.getAllByRole("listitem")
    expect(items).toHaveLength(4)
    expect(items[1]).toHaveAttribute("aria-current", "step")
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run src/components/__tests__/Stepper.test.tsx
```

Expected: FAIL — module missing.

- [ ] **Step 3: Implement Stepper**

```tsx
// frontend/src/components/ingestion/Stepper.tsx
import { Check } from "lucide-react"

import { cn } from "@/lib/utils"
import type { JobStatus } from "@/types/ingestion"

const STEPS = ["Upload", "Extract", "Review", "Finalize"] as const
export type StepIndex = 1 | 2 | 3 | 4

export function statusToStep(status: JobStatus): StepIndex {
  switch (status) {
    case "pending":          return 1
    case "extracting":       return 2
    case "ready_for_review": return 3
    case "confirmed":
    case "reconciling":
    case "completed":
    case "failed":
      return 4
  }
}

interface Props {
  activeStep: StepIndex
}

export function Stepper({ activeStep }: Props) {
  return (
    <ol className="flex w-full items-center" aria-label="Ingestion progress">
      {STEPS.map((label, idx) => {
        const step = (idx + 1) as StepIndex
        const done = step < activeStep
        const active = step === activeStep
        const isLast = idx === STEPS.length - 1
        return (
          <li
            key={label}
            aria-current={active ? "step" : undefined}
            className={cn("flex items-center", !isLast && "flex-1")}
          >
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  "flex size-7 items-center justify-center rounded-full border text-xs font-medium",
                  done && "bg-primary text-primary-foreground border-primary",
                  active && "border-primary text-primary",
                  !done && !active && "border-border text-muted-foreground",
                )}
              >
                {done ? <Check className="size-4" aria-hidden /> : step}
              </span>
              <span
                className={cn(
                  "text-sm",
                  active ? "text-foreground font-medium" : "text-muted-foreground",
                )}
              >
                {label}
              </span>
            </div>
            {!isLast && (
              <div
                className={cn(
                  "mx-3 h-px flex-1",
                  done ? "bg-primary" : "bg-border",
                )}
                aria-hidden
              />
            )}
          </li>
        )
      })}
    </ol>
  )
}
```

- [ ] **Step 4: Verify tests pass**

```bash
cd frontend && npx vitest run src/components/__tests__/Stepper.test.tsx
```

Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
cd frontend && git add src/components/ingestion/Stepper.tsx src/components/__tests__/Stepper.test.tsx
git commit -m "feat(ingestion): Stepper component + status→step mapping"
```

---

### Task 10: MultiFileDropzone

**Files:**
- Create: `frontend/src/components/ingestion/MultiFileDropzone.tsx`
- Create: `frontend/src/components/__tests__/MultiFileDropzone.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/__tests__/MultiFileDropzone.test.tsx
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { MultiFileDropzone } from "@/components/ingestion/MultiFileDropzone"

const ACCEPT = ".xlsx,.pdf,.jpg,.jpeg,.png,.heic"

function makeFile(name: string, type: string, sizeKb = 1) {
  return new File(["x".repeat(sizeKb * 1024)], name, { type })
}

describe("MultiFileDropzone", () => {
  it("calls onChange with selected files", async () => {
    const onChange = vi.fn()
    render(<MultiFileDropzone files={[]} onChange={onChange} accept={ACCEPT} />)
    const input = screen.getByLabelText(/upload files/i) as HTMLInputElement
    await userEvent.upload(input, [
      makeFile("a.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
      makeFile("b.pdf", "application/pdf"),
    ])
    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ name: "a.xlsx" }),
      expect.objectContaining({ name: "b.pdf" }),
    ])
  })

  it("renders the file list with size and remove button", async () => {
    const onChange = vi.fn()
    const files = [makeFile("a.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 50)]
    render(<MultiFileDropzone files={files} onChange={onChange} accept={ACCEPT} />)
    expect(screen.getByText("a.xlsx")).toBeInTheDocument()
    expect(screen.getByText(/50.00 KB/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: /remove a\.xlsx/i }))
    expect(onChange).toHaveBeenCalledWith([])
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run src/components/__tests__/MultiFileDropzone.test.tsx
```

Expected: FAIL — module missing.

- [ ] **Step 3: Implement MultiFileDropzone**

```tsx
// frontend/src/components/ingestion/MultiFileDropzone.tsx
import { FileSpreadsheet, FileText, Image as ImageIcon, Upload, X } from "lucide-react"
import { useRef, useState, type DragEvent } from "react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

interface Props {
  files: File[]
  onChange: (files: File[]) => void
  accept: string
  disabled?: boolean
  rejectedReasons?: Record<string, string>
  maxBytes?: number
}

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(2)} KB`
  return `${(n / 1024 / 1024).toFixed(2)} MB`
}

function iconFor(file: File) {
  if (file.type.startsWith("image/")) return ImageIcon
  if (file.type === "application/pdf") return FileText
  return FileSpreadsheet
}

export function MultiFileDropzone({
  files, onChange, accept, disabled, rejectedReasons = {}, maxBytes,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)

  function handleAdd(picked: FileList | File[]) {
    const next = [...files, ...Array.from(picked)]
    onChange(next)
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setDragOver(false)
    if (disabled) return
    handleAdd(e.dataTransfer.files)
  }

  return (
    <div className="space-y-3">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        className={cn(
          "rounded-lg border-2 border-dashed p-6 text-center transition-colors",
          dragOver ? "border-primary bg-accent" : "border-border",
          disabled && "opacity-60 pointer-events-none",
        )}
      >
        <Upload className="mx-auto size-8 text-muted-foreground" aria-hidden />
        <p className="mt-2 text-sm">
          Drag & drop files here, or
          <label htmlFor="ingestion-upload" className="ml-1 cursor-pointer text-primary underline">
            browse
            <input
              ref={inputRef}
              id="ingestion-upload"
              type="file"
              multiple
              accept={accept}
              className="sr-only"
              aria-label="Upload files"
              disabled={disabled}
              onChange={(e) => {
                if (e.target.files) handleAdd(e.target.files)
                if (inputRef.current) inputRef.current.value = ""
              }}
            />
          </label>
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          XLSX, PDF, JPG, PNG, HEIC{maxBytes ? ` · max ${fmtBytes(maxBytes)} per file` : ""}
        </p>
      </div>

      {files.length > 0 && (
        <ul className="divide-y rounded-lg border">
          {files.map((f, idx) => {
            const Icon = iconFor(f)
            const rejected = rejectedReasons[f.name]
            return (
              <li
                key={`${f.name}-${idx}`}
                className="flex items-center gap-3 p-3"
              >
                <Icon className="size-5 shrink-0 text-muted-foreground" aria-hidden />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm">{f.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {fmtBytes(f.size)}
                    {rejected && (
                      <span className="ml-2 text-destructive">· {rejected}</span>
                    )}
                  </p>
                </div>
                <Button
                  size="icon"
                  variant="ghost"
                  aria-label={`Remove ${f.name}`}
                  disabled={disabled}
                  onClick={() => onChange(files.filter((_, i) => i !== idx))}
                >
                  <X className="size-4" />
                </Button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Verify tests pass**

```bash
cd frontend && npx vitest run src/components/__tests__/MultiFileDropzone.test.tsx
```

Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
cd frontend && git add src/components/ingestion/MultiFileDropzone.tsx src/components/__tests__/MultiFileDropzone.test.tsx
git commit -m "feat(ingestion): MultiFileDropzone with drag-and-drop and file list"
```

---

### Task 11: UploadStep + IngestionNew page

**Files:**
- Create: `frontend/src/components/ingestion/UploadStep.tsx`
- Modify: `frontend/src/pages/IngestionNew.tsx` (was a stub)

- [ ] **Step 1: Implement UploadStep**

```tsx
// frontend/src/components/ingestion/UploadStep.tsx
import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"

import { MultiFileDropzone } from "@/components/ingestion/MultiFileDropzone"
import { Stepper } from "@/components/ingestion/Stepper"
import { PeriodPicker } from "@/components/reconciliation/PeriodPicker"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { useCreateJob } from "@/hooks/useIngestion"
import { ApiError } from "@/lib/api"
import type { JobKind } from "@/types/ingestion"

const ACCEPT = ".xlsx,.pdf,.jpg,.jpeg,.png,.heic"
const MAX_BYTES = 25 * 1024 * 1024 // mirrors INGESTION_MAX_FILE_SIZE_MB default

interface Props {
  clientId: string
}

export function UploadStep({ clientId }: Props) {
  const navigate = useNavigate()
  const createJob = useCreateJob()

  const [files, setFiles] = useState<File[]>([])
  const [period, setPeriod] = useState({ start: "", end: "" })
  const [kind, setKind] = useState<JobKind>("purchase_register")

  const periodError = period.start && period.end && period.end < period.start
    ? "Period end must be on or after period start" : undefined
  const oversize = files.find((f) => f.size > MAX_BYTES)
  const canSubmit = files.length > 0 && !!period.start && !!period.end && !periodError && !oversize

  async function handleSubmit() {
    if (!canSubmit) return
    try {
      const res = await createJob.mutateAsync({
        client_id: clientId,
        period_start: period.start,
        period_end: period.end,
        kind,
        files,
      })
      const rejected = res.files.filter((f) => !f.accepted)
      if (rejected.length === res.files.length) {
        toast.error("All files were rejected.")
      } else if (rejected.length > 0) {
        toast.warning(`${rejected.length} file(s) rejected; proceeding with the rest.`)
      } else {
        toast.success("Upload received. Extracting…")
      }
      navigate(`/clients/${clientId}/ingestion/${res.job_id}`)
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e as Error).message
      toast.error(msg)
    }
  }

  return (
    <div className="space-y-6">
      <Stepper activeStep={1} />

      <Card>
        <CardHeader><CardTitle>Files</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <MultiFileDropzone
            files={files}
            onChange={setFiles}
            accept={ACCEPT}
            disabled={createJob.isPending}
            maxBytes={MAX_BYTES}
            rejectedReasons={
              oversize ? { [oversize.name]: `exceeds ${MAX_BYTES / 1024 / 1024} MB` } : {}
            }
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Document type & period</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <fieldset>
            <legend className="text-sm font-medium mb-2">Document type</legend>
            <div role="radiogroup" className="flex gap-4">
              {(["purchase_register", "supplier_export"] as const).map((k) => (
                <label key={k} className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="kind"
                    value={k}
                    checked={kind === k}
                    onChange={() => setKind(k)}
                    disabled={createJob.isPending}
                  />
                  <span className="text-sm">
                    {k === "purchase_register" ? "Purchase register" : "Supplier-filed export"}
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          <div>
            <Label className="mb-2 block text-sm">Period</Label>
            <PeriodPicker
              start={period.start}
              end={period.end}
              onChange={setPeriod}
              disabled={createJob.isPending}
              errorMessage={periodError}
            />
          </div>
        </CardContent>
      </Card>

      <div className="flex items-center gap-3">
        <Button onClick={handleSubmit} disabled={!canSubmit || createJob.isPending}>
          {createJob.isPending ? "Uploading…" : `Upload ${files.length || ""} file${files.length === 1 ? "" : "s"}`.trim()}
        </Button>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Wire IngestionNew page**

```tsx
// frontend/src/pages/IngestionNew.tsx
import { useParams } from "react-router-dom"

import { UploadStep } from "@/components/ingestion/UploadStep"
import { PageHeader } from "@/components/layout/PageHeader"
import { useClient } from "@/hooks/useClients"

export function IngestionNew() {
  const { id: clientId } = useParams<{ id: string }>()
  const { data: client } = useClient(clientId)
  if (!clientId) return <p className="text-muted-foreground">Missing client id.</p>
  return (
    <div className="max-w-3xl space-y-6">
      <PageHeader
        breadcrumbs={[
          { label: "Clients", to: "/clients" },
          { label: client?.name ?? "Client", to: `/clients/${clientId}` },
          { label: "New ingestion" },
        ]}
        title="New ingestion"
        subtitle="Upload purchase-register or supplier-export documents in any format. We'll extract, you review, then finalize."
      />
      <UploadStep clientId={clientId} />
    </div>
  )
}
```

- [ ] **Step 3: Verify build & tests**

```bash
cd frontend && npm run build && npx vitest run
```

Expected: build OK, all tests pass.

- [ ] **Step 4: Commit**

```bash
cd frontend && git add src/components/ingestion/UploadStep.tsx src/pages/IngestionNew.tsx
git commit -m "feat(ingestion): UploadStep + IngestionNew page wiring"
```

---

## Phase 3 — Extracting step + polling

### Task 12: ExtractingStep + EngineBadge

**Files:**
- Create: `frontend/src/components/ingestion/EngineBadge.tsx`
- Create: `frontend/src/components/ingestion/ExtractingStep.tsx`

- [ ] **Step 1: Implement EngineBadge**

```tsx
// frontend/src/components/ingestion/EngineBadge.tsx
import { Badge } from "@/components/ui/badge"

const LABELS: Record<string, string> = {
  pandas: "Excel",
  "pandas+llm-mapper": "Excel + AI columns",
  "pdfplumber+llm": "PDF + AI",
  "gemini-vision": "AI vision",
  "tesseract+llm": "OCR + AI",
}

export function EngineBadge({ engine }: { engine: string | null | undefined }) {
  if (!engine) return null
  return <Badge variant="outline" className="font-normal">{LABELS[engine] ?? engine}</Badge>
}
```

- [ ] **Step 2: Implement ExtractingStep**

```tsx
// frontend/src/components/ingestion/ExtractingStep.tsx
import { CheckCircle2, Loader2, XCircle } from "lucide-react"

import { EngineBadge } from "@/components/ingestion/EngineBadge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import type { IngestionFileOut } from "@/types/ingestion"

interface Props {
  files: IngestionFileOut[]
  filesDone: number
  filesTotal: number
}

const ICONS: Record<IngestionFileOut["status"], typeof Loader2> = {
  queued: Loader2,
  extracting: Loader2,
  extracted: CheckCircle2,
  failed: XCircle,
  skipped: XCircle,
}

const COLORS: Record<IngestionFileOut["status"], string> = {
  queued: "text-muted-foreground",
  extracting: "text-primary",
  extracted: "text-green-600 dark:text-green-500",
  failed: "text-destructive",
  skipped: "text-muted-foreground",
}

export function ExtractingStep({ files, filesDone, filesTotal }: Props) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Extracting…</CardTitle>
        <p className="text-sm text-muted-foreground">
          {filesDone} of {filesTotal} files done. This usually takes 10-30s; AI-vision files take longer.
        </p>
      </CardHeader>
      <CardContent>
        <ul className="divide-y">
          {files.map((f) => {
            const Icon = ICONS[f.status]
            const isSpinner = f.status === "queued" || f.status === "extracting"
            return (
              <li key={f.id} className="flex items-center gap-3 py-3">
                <Icon
                  className={cn("size-5 shrink-0", COLORS[f.status], isSpinner && "animate-spin")}
                  aria-hidden
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm">{f.original_filename}</p>
                  <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                    <EngineBadge engine={f.engine} />
                    <span>{f.status}</span>
                    {f.error && <span className="text-destructive">— {f.error}</span>}
                  </div>
                </div>
                {f.status === "extracted" && (
                  <span className="text-xs text-muted-foreground">{f.rows_extracted} rows</span>
                )}
              </li>
            )
          })}
        </ul>
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 3: Commit**

```bash
cd frontend && git add src/components/ingestion/ExtractingStep.tsx src/components/ingestion/EngineBadge.tsx
git commit -m "feat(ingestion): ExtractingStep with per-file progress + EngineBadge"
```

---

## Phase 4 — Review step

### Task 13: StatusChip + WarningChip

**Files:**
- Create: `frontend/src/components/ingestion/StatusChip.tsx`
- Create: `frontend/src/components/ingestion/WarningChip.tsx`

- [ ] **Step 1: Implement StatusChip**

```tsx
// frontend/src/components/ingestion/StatusChip.tsx
import { Badge } from "@/components/ui/badge"
import type { RowStatus } from "@/types/ingestion"

const STYLES: Record<RowStatus, string> = {
  auto_passed: "bg-muted text-foreground",
  needs_review: "bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-200",
  confirmed: "bg-green-100 text-green-900 dark:bg-green-900/40 dark:text-green-200",
  rejected: "bg-red-100 text-red-900 dark:bg-red-900/40 dark:text-red-200",
  edited: "bg-blue-100 text-blue-900 dark:bg-blue-900/40 dark:text-blue-200",
}

const LABELS: Record<RowStatus, string> = {
  auto_passed: "Auto",
  needs_review: "Needs review",
  confirmed: "Confirmed",
  rejected: "Rejected",
  edited: "Edited",
}

export function StatusChip({ status }: { status: RowStatus }) {
  return <Badge className={STYLES[status]}>{LABELS[status]}</Badge>
}
```

- [ ] **Step 2: Implement WarningChip**

```tsx
// frontend/src/components/ingestion/WarningChip.tsx
import { AlertTriangle } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import type { FieldWarning } from "@/types/ingestion"

const HUMAN: Record<string, string> = {
  BIN_MISSING: "BIN missing",
  BIN_FORMAT: "BIN format invalid",
  DATE_OUT_OF_PERIOD: "Date outside period",
  VAT_RATIO_UNUSUAL: "VAT % outside 4-16%",
}

export function WarningChip({ warning }: { warning: FieldWarning }) {
  const label = HUMAN[warning.code] ?? warning.code
  return (
    <Badge variant="outline" className="gap-1 border-amber-400/60 text-amber-700 dark:text-amber-300">
      <AlertTriangle className="size-3" aria-hidden />
      <span title={warning.message}>{label}</span>
    </Badge>
  )
}
```

- [ ] **Step 3: Commit**

```bash
cd frontend && git add src/components/ingestion/StatusChip.tsx src/components/ingestion/WarningChip.tsx
git commit -m "feat(ingestion): StatusChip + WarningChip"
```

---

### Task 14: RowsTable

**Files:**
- Create: `frontend/src/components/ingestion/RowsTable.tsx`
- Create: `frontend/src/components/__tests__/RowsTable.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/__tests__/RowsTable.test.tsx
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import { RowsTable } from "@/components/ingestion/RowsTable"
import type { ExtractedRowOut } from "@/types/ingestion"

const baseRow = (overrides: Partial<ExtractedRowOut> = {}): ExtractedRowOut => ({
  id: "11111111-1111-1111-1111-111111111111",
  file_id: "22222222-2222-2222-2222-222222222222",
  job_id: "33333333-3333-3333-3333-333333333333",
  source_page_no: 1,
  row_data: {
    invoice_no: "INV-1", invoice_date: "2026-05-15",
    taxable_amount_bdt: "1000.00", vat_amount_bdt: "150.00",
    supplier_bin: "100200300", supplier_name: "ACME",
  },
  row_data_original: {
    invoice_no: "INV-1", invoice_date: "2026-05-15",
    taxable_amount_bdt: "1000.00", vat_amount_bdt: "150.00",
    supplier_bin: "100200300", supplier_name: "ACME",
  },
  status: "needs_review",
  field_warnings: [],
  reviewed_by: null, reviewed_at: null,
  created_at: "2026-05-15T12:00:00+00:00",
  ...overrides,
})

describe("RowsTable", () => {
  it("renders rows with status chips", () => {
    render(
      <RowsTable
        rows={[baseRow({ id: "a", status: "needs_review" }), baseRow({ id: "b", status: "auto_passed" })]}
        selected={new Set()}
        onToggleSelect={vi.fn()}
        onToggleSelectAll={vi.fn()}
        onRowClick={vi.fn()}
      />,
    )
    expect(screen.getByText("Needs review")).toBeInTheDocument()
    expect(screen.getByText("Auto")).toBeInTheDocument()
  })

  it("invokes onRowClick when a row is clicked", async () => {
    const onRowClick = vi.fn()
    render(
      <RowsTable
        rows={[baseRow({ id: "abc" })]}
        selected={new Set()}
        onToggleSelect={vi.fn()}
        onToggleSelectAll={vi.fn()}
        onRowClick={onRowClick}
      />,
    )
    await userEvent.click(screen.getByText("INV-1"))
    expect(onRowClick).toHaveBeenCalledWith("abc")
  })

  it("toggles select-all when header checkbox clicked", async () => {
    const onToggleSelectAll = vi.fn()
    render(
      <RowsTable
        rows={[baseRow()]}
        selected={new Set()}
        onToggleSelect={vi.fn()}
        onToggleSelectAll={onToggleSelectAll}
        onRowClick={vi.fn()}
      />,
    )
    await userEvent.click(screen.getByLabelText(/select all rows/i))
    expect(onToggleSelectAll).toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run src/components/__tests__/RowsTable.test.tsx
```

Expected: FAIL — module missing.

- [ ] **Step 3: Implement RowsTable**

```tsx
// frontend/src/components/ingestion/RowsTable.tsx
import { StatusChip } from "@/components/ingestion/StatusChip"
import { WarningChip } from "@/components/ingestion/WarningChip"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import { formatBDT } from "@/lib/formatBDT"
import type { ExtractedRowOut } from "@/types/ingestion"

interface Props {
  rows: ExtractedRowOut[]
  selected: Set<string>
  onToggleSelect: (id: string) => void
  onToggleSelectAll: () => void
  onRowClick: (id: string) => void
}

export function RowsTable({
  rows, selected, onToggleSelect, onToggleSelectAll, onRowClick,
}: Props) {
  const allSelected = rows.length > 0 && rows.every((r) => selected.has(r.id))
  return (
    <div className="rounded-lg border overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-10">
              <Checkbox
                checked={allSelected}
                onCheckedChange={onToggleSelectAll}
                aria-label="Select all rows"
              />
            </TableHead>
            <TableHead>Invoice</TableHead>
            <TableHead>Date</TableHead>
            <TableHead className="text-right">Taxable</TableHead>
            <TableHead className="text-right">VAT</TableHead>
            <TableHead>BIN</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Warnings</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((r) => {
            const bin = r.row_data.supplier_bin ?? r.row_data.buyer_bin ?? ""
            return (
              <TableRow
                key={r.id}
                className="cursor-pointer hover:bg-accent/50"
                onClick={(e) => {
                  // ignore checkbox clicks
                  if ((e.target as HTMLElement).closest("[data-row-checkbox]")) return
                  onRowClick(r.id)
                }}
              >
                <TableCell data-row-checkbox onClick={(e) => e.stopPropagation()}>
                  <Checkbox
                    checked={selected.has(r.id)}
                    onCheckedChange={() => onToggleSelect(r.id)}
                    aria-label={`Select row ${r.row_data.invoice_no}`}
                  />
                </TableCell>
                <TableCell className="font-medium">{r.row_data.invoice_no}</TableCell>
                <TableCell>{r.row_data.invoice_date}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatBDT(Number(r.row_data.taxable_amount_bdt))}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatBDT(Number(r.row_data.vat_amount_bdt))}
                </TableCell>
                <TableCell className="font-mono text-xs">{bin || "—"}</TableCell>
                <TableCell><StatusChip status={r.status} /></TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-1">
                    {r.field_warnings.map((w, i) => (
                      <WarningChip key={`${w.code}-${i}`} warning={w} />
                    ))}
                  </div>
                </TableCell>
              </TableRow>
            )
          })}
          {rows.length === 0 && (
            <TableRow>
              <TableCell colSpan={8} className="text-center text-muted-foreground py-8">
                No rows match this filter.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  )
}
```

- [ ] **Step 4: Verify tests pass**

```bash
cd frontend && npx vitest run src/components/__tests__/RowsTable.test.tsx
```

Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
cd frontend && git add src/components/ingestion/RowsTable.tsx src/components/__tests__/RowsTable.test.tsx
git commit -m "feat(ingestion): RowsTable with bulk-select and warnings"
```

---

### Task 15: SourcePreview

**Files:**
- Create: `frontend/src/components/ingestion/SourcePreview.tsx`

- [ ] **Step 1: Implement SourcePreview**

```tsx
// frontend/src/components/ingestion/SourcePreview.tsx
import { useEffect, useState } from "react"

import { api } from "@/lib/api"
import { filePreviewUrl } from "@/lib/ingestion/api"
import type { IngestionFileOut } from "@/types/ingestion"

interface Props {
  jobId: string
  file: IngestionFileOut | undefined
  pageNo: number | null | undefined
}

/**
 * Renders a preview of the source file. Fetches the streamed bytes through
 * axios so the Authorization header is attached, then makes an Object URL
 * for <img>/<embed> consumers.
 */
export function SourcePreview({ jobId, file, pageNo }: Props) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null)

  useEffect(() => {
    let revoked = false
    setObjectUrl(null)
    if (!file) return
    api.get(filePreviewUrl(jobId, file.id), { responseType: "blob" })
      .then((res) => {
        if (revoked) return
        const url = URL.createObjectURL(res.data as Blob)
        setObjectUrl(url)
      })
      .catch(() => {
        // Surface as empty preview; the drawer still works for editing.
      })
    return () => {
      revoked = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, file?.id])

  if (!file) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        No source file available for this row.
      </div>
    )
  }
  if (!objectUrl) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        Loading preview…
      </div>
    )
  }
  if (file.mime_type === "application/pdf") {
    return (
      <embed
        src={`${objectUrl}#page=${pageNo ?? 1}`}
        type="application/pdf"
        className="h-full w-full rounded border"
        aria-label={`Preview of ${file.original_filename}`}
      />
    )
  }
  if (file.mime_type.startsWith("image/")) {
    return (
      <img
        src={objectUrl}
        alt={`Preview of ${file.original_filename}`}
        className="h-full w-full rounded border object-contain"
      />
    )
  }
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
      <p>Spreadsheet preview not supported inline.</p>
      <a href={objectUrl} download={file.original_filename} className="text-primary underline">
        Download {file.original_filename}
      </a>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
cd frontend && git add src/components/ingestion/SourcePreview.tsx
git commit -m "feat(ingestion): SourcePreview component"
```

---

### Task 16: Sheet (drawer) primitive + RowDrawer

**Files:**
- Create: `frontend/src/components/ui/sheet.tsx` (shadcn primitive)
- Create: `frontend/src/components/ingestion/RowDrawer.tsx`

- [ ] **Step 1: Add the shadcn sheet primitive**

The `@radix-ui/react-dialog` package is already installed. Create the wrapper:

```tsx
// frontend/src/components/ui/sheet.tsx
import * as DialogPrimitive from "@radix-ui/react-dialog"
import { X } from "lucide-react"
import * as React from "react"

import { cn } from "@/lib/utils"

export const Sheet = DialogPrimitive.Root
export const SheetTrigger = DialogPrimitive.Trigger
export const SheetPortal = DialogPrimitive.Portal
export const SheetClose = DialogPrimitive.Close

export const SheetOverlay = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay
    ref={ref}
    className={cn(
      "fixed inset-0 z-40 bg-background/80 backdrop-blur-sm",
      "data-[state=open]:animate-in data-[state=closed]:animate-out",
      "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
      className,
    )}
    {...props}
  />
))
SheetOverlay.displayName = "SheetOverlay"

export const SheetContent = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content> & { side?: "right" | "left" }
>(({ className, children, side = "right", ...props }, ref) => (
  <SheetPortal>
    <SheetOverlay />
    <DialogPrimitive.Content
      ref={ref}
      className={cn(
        "fixed z-50 h-full w-full max-w-3xl gap-4 border-l bg-background p-6 shadow-lg",
        "data-[state=open]:animate-in data-[state=closed]:animate-out",
        side === "right" ? "right-0 top-0 data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right" : "left-0 top-0",
        className,
      )}
      {...props}
    >
      {children}
      <DialogPrimitive.Close className="absolute right-4 top-4 rounded-sm opacity-70 hover:opacity-100">
        <X className="size-4" aria-hidden />
        <span className="sr-only">Close</span>
      </DialogPrimitive.Close>
    </DialogPrimitive.Content>
  </SheetPortal>
))
SheetContent.displayName = "SheetContent"

export const SheetHeader = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("flex flex-col space-y-1.5 text-left", className)} {...props} />
)
export const SheetTitle = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Title ref={ref} className={cn("text-lg font-semibold text-foreground", className)} {...props} />
))
SheetTitle.displayName = "SheetTitle"

export const SheetDescription = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Description>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Description>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Description ref={ref} className={cn("text-sm text-muted-foreground", className)} {...props} />
))
SheetDescription.displayName = "SheetDescription"
```

- [ ] **Step 2: Implement RowDrawer**

```tsx
// frontend/src/components/ingestion/RowDrawer.tsx
import { zodResolver } from "@hookform/resolvers/zod"
import { useEffect } from "react"
import { useForm } from "react-hook-form"
import { toast } from "sonner"

import { SourcePreview } from "@/components/ingestion/SourcePreview"
import { WarningChip } from "@/components/ingestion/WarningChip"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { useConfirmRow, useEditRow, useRejectRow } from "@/hooks/useIngestion"
import { ExtractedRowDataSchema, type ExtractedRowData, type ExtractedRowOut, type IngestionFileOut } from "@/types/ingestion"

interface Props {
  jobId: string
  row: ExtractedRowOut | undefined
  file: IngestionFileOut | undefined
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function RowDrawer({ jobId, row, file, open, onOpenChange }: Props) {
  const { register, handleSubmit, reset, formState: { errors, isDirty } } =
    useForm<ExtractedRowData>({ resolver: zodResolver(ExtractedRowDataSchema) })

  const editMut = useEditRow(jobId)
  const confirmMut = useConfirmRow(jobId)
  const rejectMut = useRejectRow(jobId)

  useEffect(() => {
    if (row) reset(row.row_data)
  }, [row, reset])

  if (!row) return null

  async function onSave(values: ExtractedRowData) {
    try {
      await editMut.mutateAsync({ rowId: row!.id, body: values })
      toast.success("Row updated")
      onOpenChange(false)
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  async function onConfirm() {
    try {
      await confirmMut.mutateAsync(row!.id)
      toast.success("Row confirmed")
      onOpenChange(false)
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  async function onReject() {
    try {
      await rejectMut.mutateAsync(row!.id)
      toast.success("Row rejected")
      onOpenChange(false)
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex flex-col">
        <SheetHeader>
          <SheetTitle>Row {row.row_data.invoice_no}</SheetTitle>
          <SheetDescription>
            {file?.original_filename}{row.source_page_no ? ` · page ${row.source_page_no}` : ""}
          </SheetDescription>
        </SheetHeader>

        {row.field_warnings.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {row.field_warnings.map((w, i) => (
              <WarningChip key={`${w.code}-${i}`} warning={w} />
            ))}
          </div>
        )}

        <form onSubmit={handleSubmit(onSave)} className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="space-y-3">
            {(["invoice_no", "invoice_date", "taxable_amount_bdt", "vat_amount_bdt", "supplier_bin", "supplier_name", "buyer_bin"] as const).map((field) => (
              <div key={field} className="space-y-1">
                <Label htmlFor={field}>{field.replace(/_/g, " ")}</Label>
                <Input id={field} {...register(field)} aria-invalid={Boolean(errors[field])} />
                {errors[field] && (
                  <p className="text-xs text-destructive">{errors[field]?.message as string}</p>
                )}
              </div>
            ))}
            <div className="flex flex-wrap items-center gap-2 pt-2">
              <Button type="submit" disabled={!isDirty || editMut.isPending}>
                {editMut.isPending ? "Saving…" : "Save changes"}
              </Button>
              <Button type="button" variant="secondary" onClick={onConfirm} disabled={confirmMut.isPending}>
                Confirm as-is
              </Button>
              <Button type="button" variant="destructive" onClick={onReject} disabled={rejectMut.isPending}>
                Reject
              </Button>
            </div>
          </div>

          <div className="min-h-[420px] lg:min-h-0">
            <SourcePreview jobId={jobId} file={file} pageNo={row.source_page_no} />
          </div>
        </form>
      </SheetContent>
    </Sheet>
  )
}
```

- [ ] **Step 3: Verify build & tests**

```bash
cd frontend && npm run build && npx vitest run
```

Expected: build OK; tests still pass.

- [ ] **Step 4: Commit**

```bash
cd frontend && git add src/components/ui/sheet.tsx src/components/ingestion/RowDrawer.tsx
git commit -m "feat(ingestion): Sheet primitive + RowDrawer with editable fields and source preview"
```

---

### Task 17: ReviewStep (table + filter chips + bulk actions)

**Files:**
- Create: `frontend/src/components/ingestion/ReviewStep.tsx`

- [ ] **Step 1: Implement ReviewStep**

```tsx
// frontend/src/components/ingestion/ReviewStep.tsx
import { useMemo, useState } from "react"
import { toast } from "sonner"

import { RowDrawer } from "@/components/ingestion/RowDrawer"
import { RowsTable } from "@/components/ingestion/RowsTable"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useBulkConfirm, useJobRows } from "@/hooks/useIngestion"
import type { ExtractedRowOut, IngestionFileOut, JobOut } from "@/types/ingestion"

type Filter = "needs_review" | "all"

interface Props {
  job: JobOut
  files: IngestionFileOut[]
  onFinalize: () => void
}

export function ReviewStep({ job, files, onFinalize }: Props) {
  const [filter, setFilter] = useState<Filter>("needs_review")
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [openRowId, setOpenRowId] = useState<string | null>(null)

  const { data, isLoading } = useJobRows(job.id, filter)
  const rows: ExtractedRowOut[] = data?.rows ?? []
  const filesById = useMemo(() => new Map(files.map((f) => [f.id, f])), [files])

  const bulkConfirm = useBulkConfirm(job.id)

  function toggleSelect(id: string) {
    setSelected((s) => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }
  function toggleSelectAll() {
    if (rows.every((r) => selected.has(r.id))) {
      setSelected(new Set())
    } else {
      setSelected(new Set(rows.map((r) => r.id)))
    }
  }

  async function handleBulkConfirm() {
    if (selected.size === 0) return
    try {
      const n = await bulkConfirm.mutateAsync(Array.from(selected))
      setSelected(new Set())
      toast.success(`Confirmed ${n} row${n === 1 ? "" : "s"}`)
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  const openRow = rows.find((r) => r.id === openRowId)
  const finalizeDisabled = job.rows_needs_review > 0
  const finalizeReason = finalizeDisabled
    ? `${job.rows_needs_review} row(s) still need review`
    : undefined

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <CardTitle>Review extracted rows</CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            <FilterChip active={filter === "needs_review"} onClick={() => setFilter("needs_review")}>
              Needs review ({job.rows_needs_review})
            </FilterChip>
            <FilterChip active={filter === "all"} onClick={() => setFilter("all")}>
              All ({job.rows_total})
            </FilterChip>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {isLoading ? (
            <p className="text-sm text-muted-foreground">Loading rows…</p>
          ) : (
            <RowsTable
              rows={rows}
              selected={selected}
              onToggleSelect={toggleSelect}
              onToggleSelectAll={toggleSelectAll}
              onRowClick={(id) => setOpenRowId(id)}
            />
          )}
          <div className="flex flex-wrap items-center gap-2">
            <Button
              onClick={handleBulkConfirm}
              disabled={selected.size === 0 || bulkConfirm.isPending}
              variant="secondary"
            >
              {bulkConfirm.isPending ? "Confirming…" : `Confirm selected (${selected.size})`}
            </Button>
            <span className="flex-1" />
            <Button
              onClick={onFinalize}
              disabled={finalizeDisabled}
              title={finalizeReason}
            >
              Finalize → run reconciliation
            </Button>
          </div>
        </CardContent>
      </Card>

      <RowDrawer
        jobId={job.id}
        row={openRow}
        file={openRow ? filesById.get(openRow.file_id) : undefined}
        open={Boolean(openRowId)}
        onOpenChange={(o) => { if (!o) setOpenRowId(null) }}
      />
    </div>
  )
}

function FilterChip({ active, onClick, children }: {
  active: boolean; onClick: () => void; children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        active
          ? "rounded-full bg-primary text-primary-foreground px-3 py-1 text-xs"
          : "rounded-full border border-border text-foreground px-3 py-1 text-xs hover:bg-accent"
      }
      aria-pressed={active}
    >
      {children}
    </button>
  )
}
```

- [ ] **Step 2: Commit**

```bash
cd frontend && git add src/components/ingestion/ReviewStep.tsx
git commit -m "feat(ingestion): ReviewStep with filter chips, bulk-confirm, and drawer integration"
```

---

## Phase 5 — Finalize step + wizard wiring

### Task 18: FinalizeStep

**Files:**
- Create: `frontend/src/components/ingestion/FinalizeStep.tsx`

- [ ] **Step 1: Implement FinalizeStep**

```tsx
// frontend/src/components/ingestion/FinalizeStep.tsx
import { CheckCircle2, Loader2, XCircle } from "lucide-react"
import { useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useFinalize } from "@/hooks/useIngestion"
import type { JobOut } from "@/types/ingestion"

interface Props {
  job: JobOut
  clientId: string
}

export function FinalizeStep({ job, clientId }: Props) {
  const navigate = useNavigate()
  const finalize = useFinalize(job.id)

  // Auto-navigate when reconciliation completes
  useEffect(() => {
    if (job.status === "completed" && job.reconciliation_id) {
      toast.success("Reconciliation complete")
      navigate(`/clients/${clientId}/recon/${job.reconciliation_id}`, { replace: true })
    }
  }, [job.status, job.reconciliation_id, clientId, navigate])

  async function handleFinalize() {
    try {
      await finalize.mutateAsync()
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  if (job.status === "reconciling") {
    return (
      <Card>
        <CardHeader><CardTitle>Reconciling…</CardTitle></CardHeader>
        <CardContent>
          <div className="flex items-center gap-3 text-sm">
            <Loader2 className="size-5 animate-spin text-primary" aria-hidden />
            <p>Matching invoices against the supplier-filed export.</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (job.status === "completed") {
    return (
      <Card>
        <CardHeader><CardTitle>Done</CardTitle></CardHeader>
        <CardContent className="flex items-center gap-3 text-sm">
          <CheckCircle2 className="size-5 text-green-600 dark:text-green-500" aria-hidden />
          <p>Redirecting to the reconciliation report…</p>
        </CardContent>
      </Card>
    )
  }

  if (job.status === "failed") {
    return (
      <Card>
        <CardHeader><CardTitle>Reconciliation failed</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center gap-3 text-sm">
            <XCircle className="size-5 text-destructive" aria-hidden />
            <p>{job.error_summary || "An unexpected error occurred."}</p>
          </div>
          <Button onClick={handleFinalize} disabled={finalize.isPending}>
            Retry
          </Button>
        </CardContent>
      </Card>
    )
  }

  // 'confirmed' (or readiness state arrived here from Review)
  return (
    <Card>
      <CardHeader><CardTitle>Ready to finalize</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">
          {job.rows_total} row(s) confirmed. Click below to run reconciliation.
        </p>
        <Button onClick={handleFinalize} disabled={finalize.isPending}>
          {finalize.isPending ? "Submitting…" : "Run reconciliation"}
        </Button>
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 2: Commit**

```bash
cd frontend && git add src/components/ingestion/FinalizeStep.tsx
git commit -m "feat(ingestion): FinalizeStep with reconciling/completed/failed handling"
```

---

### Task 19: IngestionWizard + IngestionJob page

**Files:**
- Create: `frontend/src/components/ingestion/IngestionWizard.tsx`
- Modify: `frontend/src/pages/IngestionJob.tsx` (was a stub)
- Create: `frontend/src/components/__tests__/IngestionWizard.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/__tests__/IngestionWizard.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import MockAdapter from "axios-mock-adapter"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it } from "vitest"

import { IngestionWizard } from "@/components/ingestion/IngestionWizard"
import { api } from "@/lib/api"

let mock: MockAdapter
beforeEach(() => { mock = new MockAdapter(api) })
afterEach(() => { mock.restore() })

function withProviders(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

const JOB_ID = "00000000-0000-0000-0000-000000000001"
const CLIENT_ID = "00000000-0000-0000-0000-000000000010"

function jobFixture(status: string) {
  return {
    job: {
      id: JOB_ID, tenant_id: CLIENT_ID, client_id: CLIENT_ID,
      kind: "purchase_register", period_start: "2026-05-01", period_end: "2026-05-31",
      status,
      files_total: 1, files_done: 1,
      rows_total: 0, rows_needs_review: 0,
      error_summary: null, reconciliation_id: null,
      created_at: "2026-05-15T12:00:00+00:00",
      updated_at: "2026-05-15T12:00:00+00:00",
      completed_at: null,
    },
    files: [],
  }
}

describe("IngestionWizard", () => {
  it("renders ExtractingStep when status=extracting", async () => {
    mock.onGet(`/api/v1/ingestion/jobs/${JOB_ID}`).reply(200, jobFixture("extracting"))
    render(withProviders(<IngestionWizard jobId={JOB_ID} clientId={CLIENT_ID} />))
    await waitFor(() => expect(screen.getByText(/Extracting…/i)).toBeInTheDocument())
  })

  it("renders ReviewStep when status=ready_for_review", async () => {
    mock.onGet(`/api/v1/ingestion/jobs/${JOB_ID}`).reply(200, jobFixture("ready_for_review"))
    mock.onGet(`/api/v1/ingestion/jobs/${JOB_ID}/rows`).reply(200, { rows: [], total: 0, has_more: false })
    render(withProviders(<IngestionWizard jobId={JOB_ID} clientId={CLIENT_ID} />))
    await waitFor(() => expect(screen.getByText(/Review extracted rows/i)).toBeInTheDocument())
  })

  it("renders FinalizeStep when status=confirmed", async () => {
    mock.onGet(`/api/v1/ingestion/jobs/${JOB_ID}`).reply(200, jobFixture("confirmed"))
    render(withProviders(<IngestionWizard jobId={JOB_ID} clientId={CLIENT_ID} />))
    await waitFor(() => expect(screen.getByText(/Ready to finalize/i)).toBeInTheDocument())
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run src/components/__tests__/IngestionWizard.test.tsx
```

Expected: FAIL — module missing.

- [ ] **Step 3: Implement IngestionWizard**

```tsx
// frontend/src/components/ingestion/IngestionWizard.tsx
import { useState } from "react"

import { ExtractingStep } from "@/components/ingestion/ExtractingStep"
import { FinalizeStep } from "@/components/ingestion/FinalizeStep"
import { ReviewStep } from "@/components/ingestion/ReviewStep"
import { Stepper, statusToStep } from "@/components/ingestion/Stepper"
import { Card, CardContent } from "@/components/ui/card"
import { useJob } from "@/hooks/useIngestion"

interface Props {
  jobId: string
  clientId: string
}

export function IngestionWizard({ jobId, clientId }: Props) {
  const { data, isLoading, isError, error } = useJob(jobId)
  const [forceFinalize, setForceFinalize] = useState(false)

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading job…</p>
  }
  if (isError || !data) {
    return (
      <Card>
        <CardContent className="pt-6 text-sm text-destructive">
          {(error as Error)?.message ?? "Failed to load job."}
        </CardContent>
      </Card>
    )
  }

  const { job, files } = data
  const step = statusToStep(job.status)

  return (
    <div className="space-y-6">
      <Stepper activeStep={step} />
      {(job.status === "pending" || job.status === "extracting") && (
        <ExtractingStep
          files={files}
          filesDone={job.files_done}
          filesTotal={job.files_total}
        />
      )}
      {job.status === "ready_for_review" && !forceFinalize && (
        <ReviewStep
          job={job}
          files={files}
          onFinalize={() => setForceFinalize(true)}
        />
      )}
      {(job.status === "confirmed"
        || job.status === "reconciling"
        || job.status === "completed"
        || job.status === "failed"
        || (job.status === "ready_for_review" && forceFinalize)) && (
        <FinalizeStep job={job} clientId={clientId} />
      )}
    </div>
  )
}
```

> The `forceFinalize` flag handles the brief moment between the user clicking "Finalize" in `ReviewStep` and the backend transitioning the job from `ready_for_review` → `confirmed`. Without it the user would still see the review pane.

- [ ] **Step 4: Wire IngestionJob page**

```tsx
// frontend/src/pages/IngestionJob.tsx
import { useParams } from "react-router-dom"

import { IngestionWizard } from "@/components/ingestion/IngestionWizard"
import { PageHeader } from "@/components/layout/PageHeader"
import { useClient } from "@/hooks/useClients"

export function IngestionJob() {
  const { id: clientId, jobId } = useParams<{ id: string; jobId: string }>()
  const { data: client } = useClient(clientId)
  if (!clientId || !jobId) return <p className="text-muted-foreground">Missing client/job id.</p>
  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumbs={[
          { label: "Clients", to: "/clients" },
          { label: client?.name ?? "Client", to: `/clients/${clientId}` },
          { label: "Ingestion" },
        ]}
        title="Ingestion job"
      />
      <IngestionWizard jobId={jobId} clientId={clientId} />
    </div>
  )
}
```

- [ ] **Step 5: Verify tests + build**

```bash
cd frontend && npx vitest run src/components/__tests__/IngestionWizard.test.tsx && npm run build
```

Expected: tests PASS (3), build OK.

- [ ] **Step 6: Commit**

```bash
cd frontend && git add src/components/ingestion/IngestionWizard.tsx src/pages/IngestionJob.tsx src/components/__tests__/IngestionWizard.test.tsx
git commit -m "feat(ingestion): IngestionWizard status-driven step router + IngestionJob page"
```

---

## Phase 6 — Replace ReconNew entry point

### Task 20: Update ClientDetail entry point + ClientReconciliationsList CTA

**Files:**
- Modify: `frontend/src/pages/ClientDetail.tsx`
- Modify: `frontend/src/components/reconciliation/ClientReconciliationsList.tsx`

- [ ] **Step 1: Update ClientDetail "Coming in later phases" panel**

Replace the placeholder block (lines 97-102) with:

```tsx
<Card>
  <CardHeader><CardTitle>Documents & ingestion</CardTitle></CardHeader>
  <CardContent className="space-y-2">
    <p className="text-sm text-muted-foreground">
      Upload purchase-register and supplier-export documents in any format
      (XLSX, PDF, scans, photos). We'll extract, you review, then we
      reconcile against NBR data.
    </p>
    <Button asChild>
      <Link to={`/clients/${client.id}/ingestion/new`}>Start ingestion</Link>
    </Button>
  </CardContent>
</Card>
```

- [ ] **Step 2: Update ClientReconciliationsList CTA**

Find the "Run a new reconciliation" link (the search will land on the existing `/clients/:id/recon/new` href) and update it:

```bash
cd frontend && grep -n "/recon/new" src/components/reconciliation/ClientReconciliationsList.tsx
```

Replace `to={\`/clients/${clientId}/recon/new\`}` with `to={\`/clients/${clientId}/ingestion/new\`}` (label likely already says "Run a new reconciliation"; change to "Start a new ingestion" while we're here).

- [ ] **Step 3: Verify build & tests**

```bash
cd frontend && npm run build && npx vitest run
```

Expected: build OK, tests pass.

- [ ] **Step 4: Commit**

```bash
cd frontend && git add src/pages/ClientDetail.tsx src/components/reconciliation/ClientReconciliationsList.tsx
git commit -m "feat(ingestion): replace recon-new entry points with ingestion wizard"
```

---

### Task 21: Delete ReconNew.tsx

**Files:**
- Delete: `frontend/src/pages/ReconNew.tsx`

- [ ] **Step 1: Confirm no remaining references**

```bash
cd frontend && grep -rn "ReconNew\|/recon/new" src/ --include="*.ts" --include="*.tsx"
```

Expected: only the redirect in `router.tsx` remains (that's intentional — keeps old bookmarks working).

- [ ] **Step 2: Delete the file**

```bash
cd frontend && rm src/pages/ReconNew.tsx
```

- [ ] **Step 3: Verify build**

```bash
cd frontend && npm run build
```

Expected: build OK.

- [ ] **Step 4: Commit**

```bash
cd frontend && git add -A
git commit -m "chore(recon): delete ReconNew.tsx (replaced by ingestion wizard)"
```

---

## Phase 7 — Polish residue

### Task 22: Debounce client search

**Files:**
- Modify: `frontend/src/pages/Clients.tsx`
- Create: `frontend/src/hooks/useDebouncedValue.ts`
- Create: `frontend/src/hooks/__tests__/useDebouncedValue.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/hooks/__tests__/useDebouncedValue.test.tsx
import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { useDebouncedValue } from "@/hooks/useDebouncedValue"

beforeEach(() => { vi.useFakeTimers() })
afterEach(() => { vi.useRealTimers() })

describe("useDebouncedValue", () => {
  it("returns the latest value after the delay", () => {
    const { result, rerender } = renderHook(
      ({ v }: { v: string }) => useDebouncedValue(v, 250),
      { initialProps: { v: "a" } },
    )
    expect(result.current).toBe("a")
    rerender({ v: "abc" })
    expect(result.current).toBe("a")
    act(() => { vi.advanceTimersByTime(250) })
    expect(result.current).toBe("abc")
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run src/hooks/__tests__/useDebouncedValue.test.tsx
```

Expected: FAIL.

- [ ] **Step 3: Implement the hook**

```tsx
// frontend/src/hooks/useDebouncedValue.ts
import { useEffect, useState } from "react"

export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), delayMs)
    return () => clearTimeout(t)
  }, [value, delayMs])
  return v
}
```

- [ ] **Step 4: Use it in Clients.tsx**

```tsx
// frontend/src/pages/Clients.tsx
import { useState } from "react"

import { AddClientDialog } from "@/components/clients/AddClientDialog"
import { ClientsTable } from "@/components/clients/ClientsTable"
import { PageHeader } from "@/components/layout/PageHeader"
import { Input } from "@/components/ui/input"
import { useDebouncedValue } from "@/hooks/useDebouncedValue"
import { useClientsList } from "@/hooks/useClients"

export function Clients() {
  const [search, setSearch] = useState("")
  const debounced = useDebouncedValue(search, 250)
  const { data: clients = [], isLoading } = useClientsList(debounced)

  return (
    <div className="space-y-6">
      <PageHeader
        title="Clients"
        subtitle="Manage your firm's clients. Compliance deadlines are auto-generated on add."
        actions={<AddClientDialog />}
      />
      <Input
        placeholder="Search by name…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="max-w-sm"
        autoFocus
      />
      <ClientsTable clients={clients} isLoading={isLoading} />
    </div>
  )
}
```

- [ ] **Step 5: Verify**

```bash
cd frontend && npx vitest run
```

Expected: all green (104+ tests).

- [ ] **Step 6: Commit**

```bash
cd frontend && git add src/hooks/useDebouncedValue.ts src/hooks/__tests__/useDebouncedValue.test.tsx src/pages/Clients.tsx
git commit -m "perf(clients): debounce search input by 250ms"
```

---

### Task 23: Add `autoComplete` to Login + Signup forms

**Files:**
- Modify: `frontend/src/pages/Login.tsx`
- Modify: `frontend/src/pages/Signup.tsx`

- [ ] **Step 1: Add autocomplete + aria-invalid to Login**

```tsx
// frontend/src/pages/Login.tsx — replace the two Input lines:
<Input id="email" type="email" autoComplete="email"
       aria-invalid={Boolean(errors.email)}
       {...register("email")} />
{/* ... */}
<Input id="password" type="password" autoComplete="current-password"
       aria-invalid={Boolean(errors.password)}
       {...register("password")} />
```

- [ ] **Step 2: Same for Signup (use `autoComplete="new-password"`)**

```tsx
// frontend/src/pages/Signup.tsx
<Input id="email" type="email" autoComplete="email"
       aria-invalid={Boolean(errors.email)}
       {...register("email")} />
<Input id="password" type="password" autoComplete="new-password"
       aria-invalid={Boolean(errors.password)}
       {...register("password")} />
```

- [ ] **Step 3: Verify build & existing tests**

```bash
cd frontend && npm run build && npx vitest run
```

- [ ] **Step 4: Commit**

```bash
cd frontend && git add src/pages/Login.tsx src/pages/Signup.tsx
git commit -m "a11y(auth): add autoComplete + aria-invalid to login/signup forms"
```

---

### Task 24: Bring NotFound up to standard

**Files:**
- Modify: `frontend/src/pages/NotFound.tsx`

- [ ] **Step 1: Use Button + theme tokens**

```tsx
// frontend/src/pages/NotFound.tsx
import { Link } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { useAuthStore } from "@/store/auth"

export function NotFound() {
  const session = useAuthStore((s) => s.session)
  const isAuthed = Boolean(session)
  return (
    <div className="flex min-h-screen items-center justify-center bg-muted p-6">
      <Card className="max-w-md w-full text-center">
        <CardContent className="pt-6">
          <p className="text-sm font-medium uppercase tracking-wide text-muted-foreground">
            Error 404
          </p>
          <h1 className="mt-1 text-2xl font-bold text-foreground">Page not found</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            The page you're looking for doesn't exist or has been moved.
          </p>
          <div className="mt-5">
            <Button asChild>
              <Link to={isAuthed ? "/dashboard" : "/login"}>
                {isAuthed ? "Back to dashboard" : "Back to login"}
              </Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
```

- [ ] **Step 2: Verify build & tests**

```bash
cd frontend && npm run build && npx vitest run
```

- [ ] **Step 3: Commit**

```bash
cd frontend && git add src/pages/NotFound.tsx
git commit -m "polish(404): use Button + theme tokens"
```

---

### Task 25: Lint + typecheck pass

- [ ] **Step 1: Run lint**

```bash
cd frontend && npm run lint
```

Expected: no errors. Fix any introduced. Common fixes:
- `'X' is defined but never used` → drop unused import.
- `React is declared but never used` → remove.

- [ ] **Step 2: Run typecheck via tsc**

```bash
cd frontend && npx tsc --noEmit -p tsconfig.json
```

Expected: 0 errors.

- [ ] **Step 3: Run full test suite**

```bash
cd frontend && npx vitest run
```

Expected: all tests green.

- [ ] **Step 4: Commit any lint fixes**

```bash
cd frontend && git add -A
git commit -m "chore(lint): clean up imports/types after ingestion wizard work" || echo "nothing to commit"
```

---

### Task 26: Manual smoke test + tag

- [ ] **Step 1: Boot backend with ingestion enabled**

In one terminal:

```bash
cd backend
export INGESTION_ENABLED=true
export GEMINI_API_KEY="$(grep '^GEMINI_API_KEY=' .env | cut -d'=' -f2-)"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Expected log lines: `ingestion.boot.started`, `ingestion.router_registered`.

- [ ] **Step 2: Boot frontend**

```bash
cd frontend && npm run dev
```

- [ ] **Step 3: Walk through the full happy path**

- Sign in
- Toggle dark mode (sidebar) — confirm colors flip
- Navigate to a demo client (e.g., Acme Textiles)
- Click "Start ingestion" on the Documents card
- Drop `backend/tests/ingestion/fixtures/canonical_register.xlsx`
- Pick May 2026 period, kind = Purchase register
- Click Upload — observe Stepper advance + ExtractingStep
- Wait for `ready_for_review` (≤30s) — ReviewStep appears
- Click into a row — drawer opens with editable fields + source preview link
- Bulk-select all rows → Confirm selected
- Click Finalize → reconciliation runs → auto-navigates to recon report
- Hit browser-back → still works (job page reflects `completed`)

Note any UX rough edges in the commit message; we treat anything blocking as an immediate fix-task before tagging.

- [ ] **Step 4: Tag**

```bash
cd "C:/project/Hishab AI" && git tag phase-f-frontend-complete
git log -1 --format="%H %s" phase-f-frontend-complete
```

- [ ] **Step 5: Done**

Inform the user the branch is complete: `phase-f-adaptive-ingestion` carries the full backend + frontend; tag `phase-f-frontend-complete` marks the final commit. Suggest the user runs the manual smoke once before merging to `main`.

---

## Self-review notes

**Spec coverage:** Every numbered point in the brainstorm reply is covered:
- 🔴 critical items 1-6 → Tasks 1, 3, 5, 20, 23, plus form a11y in Task 23.
- 🟡 high items 7-16 → Tasks 2 (PageHeader), 22 (debounce), 3 (mobile sidebar + sign-out + Ingestion nav), 4 (ScrollRestoration + redirect), 5 (color tokens), 24 (NotFound).
- 🟢 nice-to-have 17-20 → Task 20 swaps the placeholder panel; remaining items are deliberately deferred.
- Wizard steps 1-4 → Tasks 11, 12, 17, 18, 19.
- API + hooks → Tasks 6, 7, 8.
- Drawer + preview → Tasks 13-16.
- Replace ReconNew → Tasks 20, 21.

**Placeholder scan:** No "TBD"/"add error handling" — every step shows real code or real commands.

**Type consistency:** `JobKind`, `JobStatus`, `RowStatus` enums used consistently across types/api/hooks/components. `ingestionKeys.job(id)` and `ingestionKeys.rows(id, filter)` are the only react-query keys; invalidation in mutations matches what `useJob`/`useJobRows` reads.

**Risks worth flagging in execution:**
- The `axios-mock-adapter` dep needs to land before tests in Tasks 7+ pass.
- `next-themes` requires `attribute="class"` on `<ThemeProvider>` for the `.dark { ... }` block in `index.css` to work — the plan sets that.
- The `Sheet` shadcn primitive in Task 16 must be added before `RowDrawer` imports it; Task 16 sequences them in the right order.
- The redirect for `/clients/:id/recon/new` in Task 4 uses a small inline `RedirectReconNew` helper rather than direct `<Navigate />` because it needs `useParams()`. Verify after Task 4 that visiting an old recon URL lands on the new ingestion page.
