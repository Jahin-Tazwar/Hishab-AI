# Phase B — Clients Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the full clients CRUD experience (list page with search, add/edit dialogs, client detail page with tab scaffolding, soft delete) — entirely frontend-direct-to-Supabase. On client create, automatically generate the next 12 months of compliance events via the `generate_compliance_events` Postgres function.

**Architecture:** All clients operations are frontend-direct-to-Supabase using `@supabase/supabase-js` + RLS for tenant isolation. TanStack Query manages cache + server state. React Hook Form + Zod handles forms with strict BIN/TIN validation. No backend code added in this phase.

**Tech Stack:** React 18 + TypeScript + Vite + shadcn/ui + TanStack Query + Zustand + React Hook Form + Zod + `@supabase/supabase-js`. Vitest + @testing-library/react for unit tests.

**Reference spec:** [`docs/superpowers/specs/2026-05-02-hishabai-mvp-design.md`](../specs/2026-05-02-hishabai-mvp-design.md) Sections 6.2 (clients table), 7 (none — Phase C), 8 (calendar generation function), 9 (Clients screen routes).

**Reference plan:** [`docs/superpowers/plans/2026-05-02-phase-a-foundation.md`](2026-05-02-phase-a-foundation.md) (foundation work this builds on).

**Acceptance criteria for Phase B:**
1. Add 5 clients with mixed entity types (company, individual, partnership, ngo, bank) via the Add Client dialog. Each shows up in the list immediately.
2. Each client's `compliance_events` table has correct upcoming deadlines populated based on entity_type (verified via Supabase SQL).
3. Edit a client's name and entity_type → list reflects the change immediately (TanStack cache invalidation works).
4. Delete a client → it disappears from the list (soft delete: `deleted_at IS NOT NULL`). Audit log captures the soft-delete UPDATE.
5. Search field filters the list by client name (case-insensitive).
6. BIN/TIN format validation works: typing "abc" or 8 digits in BIN shows an inline error.
7. Cross-tenant isolation: a different user cannot see this firm's clients (RLS verified).
8. Frontend tests pass for Zod schema validation.

---

## File structure (Phase B)

**New files:**
- `frontend/src/types/client.ts` — TypeScript types + Zod schemas for clients
- `frontend/src/hooks/useClients.ts` — TanStack Query hooks (list, get, create, update, soft-delete)
- `frontend/src/components/clients/ClientForm.tsx` — reusable form (used by Add and Edit dialogs)
- `frontend/src/components/clients/AddClientDialog.tsx` — create dialog + calls `generate_compliance_events`
- `frontend/src/components/clients/EditClientDialog.tsx` — update dialog
- `frontend/src/components/clients/DeleteClientDialog.tsx` — soft-delete confirmation
- `frontend/src/components/clients/EntityTypeBadge.tsx` — color-coded badge for entity_type
- `frontend/src/components/clients/ClientsTable.tsx` — the table view (extracted from page for testability)
- `frontend/src/pages/Clients.tsx` — `/clients` list page (search + add + table)
- `frontend/src/pages/ClientDetail.tsx` — `/clients/:id` profile page with tab scaffolding
- `frontend/src/lib/format.ts` — small frontend-side BDT/date formatters (mirrors `app/core/formatting.py`)
- `frontend/vitest.config.ts` — Vitest configuration
- `frontend/src/test/setup.ts` — RTL/jsdom test setup
- `frontend/src/types/__tests__/client.test.ts` — Zod schema unit tests

**Files modified:**
- `frontend/src/router.tsx` — add `/clients` and `/clients/:id` routes (replace placeholder routes)
- `frontend/src/components/layout/AppShell.tsx` — already has Clients nav link; no change needed (verify)
- `frontend/src/components/ui/badge.tsx` — install via shadcn (used by EntityTypeBadge)
- `frontend/src/components/ui/select.tsx` — install via shadcn (used by ClientForm)
- `frontend/src/components/ui/checkbox.tsx` — install via shadcn (used by ClientForm)
- `frontend/src/components/ui/textarea.tsx` — install via shadcn (used by ClientForm for notes)
- `frontend/package.json` — add `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `jsdom` dev deps
- `frontend/.gitignore` (if any) — no changes needed

**No backend changes in Phase B.**

---

## Task 1: Install missing shadcn components + Vitest

**Files:**
- Add: `frontend/src/components/ui/badge.tsx`, `select.tsx`, `checkbox.tsx`, `textarea.tsx` (via shadcn CLI)
- Add: `frontend/vitest.config.ts`, `frontend/src/test/setup.ts`
- Modify: `frontend/package.json` (Vitest deps)

- [ ] **Step 1: Install shadcn components**

```bash
cd "C:/project/Hishab AI/frontend"
npx shadcn@latest add badge select checkbox textarea
```

Expected: 4 new files in `src/components/ui/`. shadcn may add radix dependencies — accept install prompts.

- [ ] **Step 2: Install Vitest dev dependencies**

```bash
npm install -D vitest@^2.1.0 @testing-library/react@^16.0.0 @testing-library/jest-dom@^6.5.0 jsdom@^25.0.0 @vitest/ui@^2.1.0
```

- [ ] **Step 3: Create `frontend/vitest.config.ts`**

```typescript
import path from "node:path"
import { defineConfig } from "vitest/config"

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
})
```

- [ ] **Step 4: Create `frontend/src/test/setup.ts`**

```typescript
import "@testing-library/jest-dom"
```

- [ ] **Step 5: Add `test` script to `package.json`**

Edit `frontend/package.json` `"scripts"` block to add:
```json
"test": "vitest run",
"test:watch": "vitest"
```

- [ ] **Step 6: Verify Vitest runs (no tests yet, but the runner should start cleanly)**

```bash
cd "C:/project/Hishab AI/frontend" && npm run test
```

Expected: "No test files found" (not an error).

- [ ] **Step 7: Verify build still passes**

```bash
npm run build
```

Expected: success.

- [ ] **Step 8: Commit**

```bash
cd "C:/project/Hishab AI"
git add frontend/
git commit -m "feat(frontend): add badge/select/checkbox/textarea shadcn components and Vitest setup"
```

---

## Task 2: Client types + Zod schema

**Files:**
- Create: `frontend/src/types/client.ts`
- Create: `frontend/src/types/__tests__/client.test.ts`

- [ ] **Step 1: Write the failing test first**

Create `frontend/src/types/__tests__/client.test.ts`:

```typescript
import { describe, expect, it } from "vitest"

import { clientFormSchema, ENTITY_TYPES, type ClientFormInput } from "../client"

describe("clientFormSchema", () => {
  const validBase: ClientFormInput = {
    name: "Acme Ltd",
    entity_type: "company",
    fiscal_year_end: "06-30",
    is_vat_registered: false,
  }

  it("accepts a minimal valid client", () => {
    expect(clientFormSchema.safeParse(validBase).success).toBe(true)
  })

  it("rejects empty name", () => {
    const result = clientFormSchema.safeParse({ ...validBase, name: "" })
    expect(result.success).toBe(false)
  })

  it("accepts a 12-digit TIN", () => {
    const result = clientFormSchema.safeParse({ ...validBase, tin: "123456789012" })
    expect(result.success).toBe(true)
  })

  it("rejects an 11-digit TIN", () => {
    const result = clientFormSchema.safeParse({ ...validBase, tin: "12345678901" })
    expect(result.success).toBe(false)
  })

  it("rejects non-numeric TIN", () => {
    const result = clientFormSchema.safeParse({ ...validBase, tin: "abcdefghijkl" })
    expect(result.success).toBe(false)
  })

  it("treats empty TIN as valid (optional)", () => {
    expect(clientFormSchema.safeParse({ ...validBase, tin: "" }).success).toBe(true)
  })

  it("accepts a 9-digit BIN", () => {
    expect(clientFormSchema.safeParse({ ...validBase, bin: "123456789" }).success).toBe(true)
  })

  it("rejects an 8-digit BIN", () => {
    expect(clientFormSchema.safeParse({ ...validBase, bin: "12345678" }).success).toBe(false)
  })

  it("rejects invalid email", () => {
    expect(
      clientFormSchema.safeParse({ ...validBase, contact_email: "not-an-email" }).success,
    ).toBe(false)
  })

  it("treats empty email as valid", () => {
    expect(clientFormSchema.safeParse({ ...validBase, contact_email: "" }).success).toBe(true)
  })

  it("rejects an unknown entity_type", () => {
    const result = clientFormSchema.safeParse({ ...validBase, entity_type: "alien" as never })
    expect(result.success).toBe(false)
  })

  it("rejects bad fiscal_year_end format", () => {
    const result = clientFormSchema.safeParse({ ...validBase, fiscal_year_end: "June 30" })
    expect(result.success).toBe(false)
  })

  it("ENTITY_TYPES contains the expected 5 values", () => {
    expect(ENTITY_TYPES).toEqual(["company", "individual", "partnership", "ngo", "bank"])
  })
})
```

- [ ] **Step 2: Run test (should fail — file doesn't exist)**

```bash
cd "C:/project/Hishab AI/frontend" && npm run test
```

Expected: import error (`Cannot find module '../client'`).

- [ ] **Step 3: Create `frontend/src/types/client.ts`**

```typescript
import { z } from "zod"

export const ENTITY_TYPES = [
  "company",
  "individual",
  "partnership",
  "ngo",
  "bank",
] as const

export type EntityType = (typeof ENTITY_TYPES)[number]

const optionalBdId = (digits: number, label: string) =>
  z
    .string()
    .optional()
    .refine(
      (val) => !val || new RegExp(`^\\d{${digits}}$`).test(val),
      `${label} must be exactly ${digits} digits`,
    )

const optionalEmail = z
  .string()
  .optional()
  .refine((val) => !val || z.string().email().safeParse(val).success, "Invalid email")

/**
 * The form input shape (what the user enters in the Add/Edit dialog).
 * Differs from the DB row shape — no id, tenant_id, created_at, etc.
 */
export const clientFormSchema = z.object({
  name: z.string().min(2, "Name must be at least 2 characters"),
  name_bn: z.string().optional(),
  tin: optionalBdId(12, "TIN"),
  bin: optionalBdId(9, "BIN"),
  entity_type: z.enum(ENTITY_TYPES),
  industry: z.string().optional(),
  fiscal_year_end: z
    .string()
    .regex(/^\d{2}-\d{2}$/, "Format: MM-DD (e.g. 06-30)"),
  is_vat_registered: z.boolean(),
  contact_email: optionalEmail,
  contact_phone: z.string().optional(),
  notes: z.string().optional(),
})

export type ClientFormInput = z.infer<typeof clientFormSchema>

/**
 * The full client row shape as stored in Supabase.
 */
export interface Client extends ClientFormInput {
  id: string
  tenant_id: string
  deleted_at: string | null
  created_at: string
  updated_at: string
  created_by: string
}

export const ENTITY_TYPE_LABELS: Record<EntityType, string> = {
  company: "Company",
  individual: "Individual",
  partnership: "Partnership",
  ngo: "NGO",
  bank: "Bank",
}
```

- [ ] **Step 4: Run tests (should pass)**

```bash
npm run test
```

Expected: 13 tests passing.

- [ ] **Step 5: Commit**

```bash
cd "C:/project/Hishab AI"
git add frontend/src/types/
git commit -m "feat(frontend): add Client type definitions and Zod form schema with BIN/TIN validation"
```

---

## Task 3: useClients hooks (TanStack Query)

**Files:**
- Create: `frontend/src/hooks/useClients.ts`

- [ ] **Step 1: Create `frontend/src/hooks/useClients.ts`**

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { useUserProfile } from "@/hooks/useUserProfile"
import { supabase } from "@/lib/supabase"
import { useAuthStore } from "@/store/auth"
import type { Client, ClientFormInput } from "@/types/client"

export const clientKeys = {
  all: ["clients"] as const,
  list: (search?: string) => ["clients", "list", { search: search ?? "" }] as const,
  detail: (id: string) => ["clients", "detail", id] as const,
}

/**
 * List all non-deleted clients for the current tenant. RLS handles isolation.
 * Optional case-insensitive search by name.
 */
export function useClientsList(search?: string) {
  return useQuery({
    queryKey: clientKeys.list(search),
    queryFn: async (): Promise<Client[]> => {
      let query = supabase
        .from("clients")
        .select("*")
        .is("deleted_at", null)
        .order("name", { ascending: true })

      if (search && search.trim() !== "") {
        query = query.ilike("name", `%${search.trim()}%`)
      }

      const { data, error } = await query
      if (error) throw error
      return (data ?? []) as Client[]
    },
  })
}

/**
 * Single client by id (excludes soft-deleted).
 */
export function useClient(id: string | undefined) {
  return useQuery({
    queryKey: clientKeys.detail(id ?? ""),
    enabled: Boolean(id),
    queryFn: async (): Promise<Client | null> => {
      if (!id) return null
      const { data, error } = await supabase
        .from("clients")
        .select("*")
        .eq("id", id)
        .is("deleted_at", null)
        .maybeSingle()
      if (error) throw error
      return (data as Client | null) ?? null
    },
  })
}

/**
 * Create a client + generate compliance events for the next 12 months.
 * Both run in sequence; if event generation fails the client still exists
 * (the user gets a toast, can retry from detail page in Phase D).
 */
export function useCreateClient() {
  const queryClient = useQueryClient()
  const userId = useAuthStore((s) => s.user?.id)
  const { data: profile } = useUserProfile()
  const tenantId = profile?.tenant_id

  return useMutation({
    mutationFn: async (
      input: ClientFormInput,
    ): Promise<{ client: Client; eventsGenerated: number | null }> => {
      if (!userId || !tenantId) throw new Error("Not authenticated or tenant not loaded")

      // Normalize empty strings → null for optional ID fields
      const row = {
        ...input,
        tin: input.tin?.trim() || null,
        bin: input.bin?.trim() || null,
        contact_email: input.contact_email?.trim() || null,
        contact_phone: input.contact_phone?.trim() || null,
        name_bn: input.name_bn?.trim() || null,
        industry: input.industry?.trim() || null,
        notes: input.notes?.trim() || null,
        tenant_id: tenantId,
        created_by: userId,
      }

      const { data: created, error: insertError } = await supabase
        .from("clients")
        .insert(row)
        .select()
        .single()
      if (insertError) throw insertError

      // Generate compliance events for the next 12 months
      const today = new Date().toISOString().slice(0, 10)
      const oneYearOut = new Date()
      oneYearOut.setFullYear(oneYearOut.getFullYear() + 1)
      const toDate = oneYearOut.toISOString().slice(0, 10)

      const { data: eventsCount, error: rpcError } = await supabase.rpc(
        "generate_compliance_events",
        {
          p_client_id: created.id,
          p_from_date: today,
          p_to_date: toDate,
        },
      )

      // Don't throw on RPC failure — client is already created. Surface as null.
      const eventsGenerated = rpcError ? null : (eventsCount as number)

      return { client: created as Client, eventsGenerated }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: clientKeys.all })
    },
  })
}

export function useUpdateClient() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({
      id,
      input,
    }: {
      id: string
      input: ClientFormInput
    }): Promise<Client> => {
      const row = {
        ...input,
        tin: input.tin?.trim() || null,
        bin: input.bin?.trim() || null,
        contact_email: input.contact_email?.trim() || null,
        contact_phone: input.contact_phone?.trim() || null,
        name_bn: input.name_bn?.trim() || null,
        industry: input.industry?.trim() || null,
        notes: input.notes?.trim() || null,
        updated_at: new Date().toISOString(),
      }

      const { data, error } = await supabase
        .from("clients")
        .update(row)
        .eq("id", id)
        .select()
        .single()
      if (error) throw error
      return data as Client
    },
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: clientKeys.all })
      queryClient.setQueryData(clientKeys.detail(updated.id), updated)
    },
  })
}

/**
 * Soft delete: set deleted_at = now(). The list query filters these out.
 */
export function useDeleteClient() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (id: string): Promise<void> => {
      const { error } = await supabase
        .from("clients")
        .update({ deleted_at: new Date().toISOString() })
        .eq("id", id)
      if (error) throw error
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: clientKeys.all })
    },
  })
}
```

- [ ] **Step 2: Verify build (no test yet — hooks exercised in the manual acceptance test, Task 13)**

```bash
cd "C:/project/Hishab AI/frontend" && npm run build
```

Expected: success.

- [ ] **Step 3: Commit**

```bash
cd "C:/project/Hishab AI"
git add frontend/src/hooks/useClients.ts
git commit -m "feat(frontend): add useClients TanStack Query hooks (list, get, create, update, soft-delete)"
```

---

## Task 4: ClientForm component

**Files:**
- Create: `frontend/src/components/clients/ClientForm.tsx`

- [ ] **Step 1: Create `frontend/src/components/clients/ClientForm.tsx`**

```tsx
import { zodResolver } from "@hookform/resolvers/zod"
import { useForm } from "react-hook-form"

import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import {
  clientFormSchema,
  ENTITY_TYPES,
  ENTITY_TYPE_LABELS,
  type ClientFormInput,
  type EntityType,
} from "@/types/client"

interface Props {
  defaultValues?: Partial<ClientFormInput>
  submitting?: boolean
  submitLabel?: string
  onSubmit: (values: ClientFormInput) => void
  onCancel: () => void
}

export function ClientForm({
  defaultValues,
  submitting,
  submitLabel = "Save",
  onSubmit,
  onCancel,
}: Props) {
  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm<ClientFormInput>({
    resolver: zodResolver(clientFormSchema),
    defaultValues: {
      entity_type: "company",
      fiscal_year_end: "06-30",
      is_vat_registered: false,
      ...defaultValues,
    },
  })

  const entityType = watch("entity_type")
  const isVatRegistered = watch("is_vat_registered")

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1">
          <Label htmlFor="name">Name *</Label>
          <Input id="name" {...register("name")} placeholder="e.g. Acme Industries Ltd" />
          {errors.name && <p className="text-sm text-red-600">{errors.name.message}</p>}
        </div>
        <div className="space-y-1">
          <Label htmlFor="name_bn">Name (Bangla)</Label>
          <Input id="name_bn" {...register("name_bn")} placeholder="e.g. অ্যাকমে ইন্ডাস্ট্রিজ" />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1">
          <Label htmlFor="entity_type">Entity type *</Label>
          <Select
            value={entityType}
            onValueChange={(v) => setValue("entity_type", v as EntityType, { shouldValidate: true })}
          >
            <SelectTrigger id="entity_type">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ENTITY_TYPES.map((t) => (
                <SelectItem key={t} value={t}>
                  {ENTITY_TYPE_LABELS[t]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="industry">Industry</Label>
          <Input id="industry" {...register("industry")} placeholder="e.g. Manufacturing" />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1">
          <Label htmlFor="tin">TIN (12 digits)</Label>
          <Input id="tin" {...register("tin")} placeholder="123456789012" maxLength={12} />
          {errors.tin && <p className="text-sm text-red-600">{errors.tin.message}</p>}
        </div>
        <div className="space-y-1">
          <Label htmlFor="bin">BIN (9 digits)</Label>
          <Input id="bin" {...register("bin")} placeholder="123456789" maxLength={9} />
          {errors.bin && <p className="text-sm text-red-600">{errors.bin.message}</p>}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 items-end">
        <div className="space-y-1">
          <Label htmlFor="fiscal_year_end">Fiscal year end (MM-DD)</Label>
          <Input
            id="fiscal_year_end"
            {...register("fiscal_year_end")}
            placeholder="06-30"
            maxLength={5}
          />
          {errors.fiscal_year_end && (
            <p className="text-sm text-red-600">{errors.fiscal_year_end.message}</p>
          )}
        </div>
        <div className="flex items-center gap-2 pb-2">
          <Checkbox
            id="is_vat_registered"
            checked={isVatRegistered}
            onCheckedChange={(c) => setValue("is_vat_registered", Boolean(c))}
          />
          <Label htmlFor="is_vat_registered" className="cursor-pointer">
            VAT registered
          </Label>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1">
          <Label htmlFor="contact_email">Contact email</Label>
          <Input
            id="contact_email"
            type="email"
            {...register("contact_email")}
            placeholder="contact@client.com"
          />
          {errors.contact_email && (
            <p className="text-sm text-red-600">{errors.contact_email.message}</p>
          )}
        </div>
        <div className="space-y-1">
          <Label htmlFor="contact_phone">Contact phone</Label>
          <Input id="contact_phone" {...register("contact_phone")} placeholder="+8801XXXXXXXXX" />
        </div>
      </div>

      <div className="space-y-1">
        <Label htmlFor="notes">Notes</Label>
        <Textarea id="notes" {...register("notes")} rows={3} />
      </div>

      <div className="flex justify-end gap-2 pt-2">
        <Button type="button" variant="outline" onClick={onCancel} disabled={submitting}>
          Cancel
        </Button>
        <Button type="submit" disabled={submitting}>
          {submitting ? "Saving…" : submitLabel}
        </Button>
      </div>
    </form>
  )
}
```

- [ ] **Step 2: Verify build**

```bash
cd "C:/project/Hishab AI/frontend" && npm run build
```

Expected: success.

- [ ] **Step 3: Commit**

```bash
cd "C:/project/Hishab AI"
git add frontend/src/components/clients/ClientForm.tsx
git commit -m "feat(frontend): add reusable ClientForm component with BIN/TIN/email validation"
```

---

## Task 5: AddClientDialog (creates client + generates events)

**Files:**
- Create: `frontend/src/components/clients/AddClientDialog.tsx`

- [ ] **Step 1: Create `frontend/src/components/clients/AddClientDialog.tsx`**

```tsx
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
```

- [ ] **Step 2: Verify build**

```bash
cd "C:/project/Hishab AI/frontend" && npm run build
```

- [ ] **Step 3: Commit**

```bash
cd "C:/project/Hishab AI"
git add frontend/src/components/clients/AddClientDialog.tsx
git commit -m "feat(frontend): add AddClientDialog (creates client + generates compliance events)"
```

---

## Task 6: EditClientDialog

**Files:**
- Create: `frontend/src/components/clients/EditClientDialog.tsx`

- [ ] **Step 1: Create `frontend/src/components/clients/EditClientDialog.tsx`**

```tsx
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
```

- [ ] **Step 2: Verify build**

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/clients/EditClientDialog.tsx
git commit -m "feat(frontend): add EditClientDialog component"
```

---

## Task 7: DeleteClientDialog (soft delete with confirmation)

**Files:**
- Create: `frontend/src/components/clients/DeleteClientDialog.tsx`

- [ ] **Step 1: Create `frontend/src/components/clients/DeleteClientDialog.tsx`**

```tsx
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
```

- [ ] **Step 2: Verify build**

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/clients/DeleteClientDialog.tsx
git commit -m "feat(frontend): add DeleteClientDialog with soft-delete confirmation"
```

---

## Task 8: EntityTypeBadge

**Files:**
- Create: `frontend/src/components/clients/EntityTypeBadge.tsx`

- [ ] **Step 1: Create `frontend/src/components/clients/EntityTypeBadge.tsx`**

```tsx
import { Badge } from "@/components/ui/badge"
import { ENTITY_TYPE_LABELS, type EntityType } from "@/types/client"

const STYLE: Record<EntityType, string> = {
  company: "bg-blue-100 text-blue-800 hover:bg-blue-100",
  individual: "bg-green-100 text-green-800 hover:bg-green-100",
  partnership: "bg-purple-100 text-purple-800 hover:bg-purple-100",
  ngo: "bg-amber-100 text-amber-800 hover:bg-amber-100",
  bank: "bg-slate-200 text-slate-800 hover:bg-slate-200",
}

export function EntityTypeBadge({ type }: { type: EntityType }) {
  return (
    <Badge variant="secondary" className={STYLE[type]}>
      {ENTITY_TYPE_LABELS[type]}
    </Badge>
  )
}
```

- [ ] **Step 2: Verify build**

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/clients/EntityTypeBadge.tsx
git commit -m "feat(frontend): add EntityTypeBadge color-coded by entity type"
```

---

## Task 9: ClientsTable

**Files:**
- Create: `frontend/src/components/clients/ClientsTable.tsx`

- [ ] **Step 1: Create `frontend/src/components/clients/ClientsTable.tsx`**

```tsx
import { Link } from "react-router-dom"
import { useState } from "react"
import { MoreHorizontal } from "lucide-react"

import { DeleteClientDialog } from "@/components/clients/DeleteClientDialog"
import { EditClientDialog } from "@/components/clients/EditClientDialog"
import { EntityTypeBadge } from "@/components/clients/EntityTypeBadge"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { Client } from "@/types/client"

interface Props {
  clients: Client[]
  isLoading: boolean
}

export function ClientsTable({ clients, isLoading }: Props) {
  const [editing, setEditing] = useState<Client | null>(null)
  const [deleting, setDeleting] = useState<Client | null>(null)

  if (isLoading) {
    return <div className="text-slate-500 py-8 text-center">Loading clients…</div>
  }

  if (clients.length === 0) {
    return (
      <div className="text-slate-500 py-12 text-center border border-dashed rounded">
        No clients yet. Add your first client using the button above.
      </div>
    )
  }

  return (
    <>
      <div className="rounded border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Entity type</TableHead>
              <TableHead>BIN</TableHead>
              <TableHead>TIN</TableHead>
              <TableHead>VAT registered</TableHead>
              <TableHead className="w-12" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {clients.map((c) => (
              <TableRow key={c.id}>
                <TableCell>
                  <Link to={`/clients/${c.id}`} className="font-medium text-slate-900 hover:underline">
                    {c.name}
                  </Link>
                  {c.name_bn && <div className="text-xs text-slate-500">{c.name_bn}</div>}
                </TableCell>
                <TableCell>
                  <EntityTypeBadge type={c.entity_type} />
                </TableCell>
                <TableCell className="font-mono text-sm">{c.bin ?? "—"}</TableCell>
                <TableCell className="font-mono text-sm">{c.tin ?? "—"}</TableCell>
                <TableCell>{c.is_vat_registered ? "Yes" : "No"}</TableCell>
                <TableCell>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="sm">
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onClick={() => setEditing(c)}>Edit</DropdownMenuItem>
                      <DropdownMenuItem
                        className="text-red-600 focus:text-red-700"
                        onClick={() => setDeleting(c)}
                      >
                        Delete
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {editing && (
        <EditClientDialog
          client={editing}
          open={Boolean(editing)}
          onOpenChange={(o) => !o && setEditing(null)}
        />
      )}
      {deleting && (
        <DeleteClientDialog
          client={deleting}
          open={Boolean(deleting)}
          onOpenChange={(o) => !o && setDeleting(null)}
        />
      )}
    </>
  )
}
```

- [ ] **Step 2: Verify build**

```bash
cd "C:/project/Hishab AI/frontend" && npm run build
```

`lucide-react` is already installed (it came with shadcn). If `lucide-react` is missing for some reason: `npm install lucide-react`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/clients/ClientsTable.tsx
git commit -m "feat(frontend): add ClientsTable with edit/delete dropdown actions"
```

---

## Task 10: Clients list page

**Files:**
- Create: `frontend/src/pages/Clients.tsx`

- [ ] **Step 1: Replace `frontend/src/pages/Clients.tsx`** (it doesn't exist yet — Phase A only had Login/Signup/Onboard/Dashboard placeholders)

```tsx
import { useState } from "react"

import { AddClientDialog } from "@/components/clients/AddClientDialog"
import { ClientsTable } from "@/components/clients/ClientsTable"
import { Input } from "@/components/ui/input"
import { useClientsList } from "@/hooks/useClients"

export function Clients() {
  const [search, setSearch] = useState("")
  const { data: clients = [], isLoading } = useClientsList(search)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Clients</h1>
          <p className="text-slate-600 mt-1">
            Manage your firm's clients. Compliance deadlines are auto-generated on add.
          </p>
        </div>
        <AddClientDialog />
      </div>

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

- [ ] **Step 2: Verify build**

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Clients.tsx
git commit -m "feat(frontend): add Clients list page (search + table + Add Client)"
```

---

## Task 11: ClientDetail page

**Files:**
- Create: `frontend/src/pages/ClientDetail.tsx`

- [ ] **Step 1: Create `frontend/src/pages/ClientDetail.tsx`**

```tsx
import { useState } from "react"
import { Link, useParams } from "react-router-dom"

import { DeleteClientDialog } from "@/components/clients/DeleteClientDialog"
import { EditClientDialog } from "@/components/clients/EditClientDialog"
import { EntityTypeBadge } from "@/components/clients/EntityTypeBadge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useClient } from "@/hooks/useClients"

export function ClientDetail() {
  const { id } = useParams<{ id: string }>()
  const { data: client, isLoading } = useClient(id)
  const [editing, setEditing] = useState(false)
  const [deleting, setDeleting] = useState(false)

  if (isLoading) {
    return <div className="text-slate-500 p-8">Loading client…</div>
  }

  if (!client) {
    return (
      <div className="space-y-4 p-8">
        <p className="text-slate-700">Client not found or has been deleted.</p>
        <Link to="/clients" className="text-slate-900 underline">
          Back to clients
        </Link>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <Link to="/clients" className="text-sm text-slate-500 hover:underline">
            ← Clients
          </Link>
          <h1 className="text-2xl font-bold text-slate-900 mt-1">{client.name}</h1>
          {client.name_bn && <p className="text-slate-600">{client.name_bn}</p>}
          <div className="mt-2">
            <EntityTypeBadge type={client.entity_type} />
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setEditing(true)}>
            Edit
          </Button>
          <Button variant="destructive" onClick={() => setDeleting(true)}>
            Delete
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Identifiers</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Field label="TIN" value={client.tin} mono />
            <Field label="BIN" value={client.bin} mono />
            <Field label="VAT registered" value={client.is_vat_registered ? "Yes" : "No"} />
            <Field label="Industry" value={client.industry} />
            <Field label="Fiscal year end" value={client.fiscal_year_end} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Contact</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Field label="Email" value={client.contact_email} />
            <Field label="Phone" value={client.contact_phone} />
          </CardContent>
        </Card>
      </div>

      {client.notes && (
        <Card>
          <CardHeader>
            <CardTitle>Notes</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-slate-700 whitespace-pre-wrap">{client.notes}</p>
          </CardContent>
        </Card>
      )}

      <div className="border-t pt-6">
        <h2 className="text-lg font-semibold text-slate-900">Coming in later phases</h2>
        <p className="text-sm text-slate-600 mt-1">
          Reconciliations (Phase C), Documents (Phase C), Compliance Calendar (Phase D) — these
          tabs will appear here once their phases ship.
        </p>
      </div>

      <EditClientDialog client={client} open={editing} onOpenChange={setEditing} />
      <DeleteClientDialog
        client={client}
        open={deleting}
        onOpenChange={setDeleting}
        onDeleted={() => {
          // Navigate back to list after delete
          window.location.href = "/clients"
        }}
      />
    </div>
  )
}

function Field({ label, value, mono }: { label: string; value: string | null | undefined; mono?: boolean }) {
  return (
    <div className="grid grid-cols-3 gap-2">
      <span className="text-slate-500">{label}</span>
      <span className={`col-span-2 ${mono ? "font-mono" : ""}`}>{value || "—"}</span>
    </div>
  )
}
```

- [ ] **Step 2: Verify build**

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ClientDetail.tsx
git commit -m "feat(frontend): add ClientDetail page with profile cards and edit/delete actions"
```

---

## Task 12: Wire up routes

**Files:**
- Modify: `frontend/src/router.tsx`

- [ ] **Step 1: Read the existing router**

```bash
cat "C:/project/Hishab AI/frontend/src/router.tsx"
```

- [ ] **Step 2: Edit `frontend/src/router.tsx` to add `/clients` and `/clients/:id` routes**

The current router (from Phase A) has Login/Signup/Onboard/Dashboard. Add two new routes inside the same authenticated section. The result should look like this (replace the entire file):

```tsx
import { createBrowserRouter, Navigate } from "react-router-dom"

import { AppShell } from "@/components/layout/AppShell"
import { AuthLayout } from "@/components/layout/AuthLayout"
import { RequireAuth } from "@/components/RequireAuth"
import { RequireTenant } from "@/components/RequireTenant"
import { ClientDetail } from "@/pages/ClientDetail"
import { Clients } from "@/pages/Clients"
import { Dashboard } from "@/pages/Dashboard"
import { Login } from "@/pages/Login"
import { Onboard } from "@/pages/Onboard"
import { Signup } from "@/pages/Signup"

export const router = createBrowserRouter([
  { path: "/", element: <Navigate to="/login" replace /> },
  { path: "/login", element: <AuthLayout><Login /></AuthLayout> },
  { path: "/signup", element: <AuthLayout><Signup /></AuthLayout> },
  {
    path: "/onboard",
    element: (
      <RequireAuth>
        <AuthLayout><Onboard /></AuthLayout>
      </RequireAuth>
    ),
  },
  {
    path: "/dashboard",
    element: (
      <RequireAuth>
        <RequireTenant>
          <AppShell><Dashboard /></AppShell>
        </RequireTenant>
      </RequireAuth>
    ),
  },
  {
    path: "/clients",
    element: (
      <RequireAuth>
        <RequireTenant>
          <AppShell><Clients /></AppShell>
        </RequireTenant>
      </RequireAuth>
    ),
  },
  {
    path: "/clients/:id",
    element: (
      <RequireAuth>
        <RequireTenant>
          <AppShell><ClientDetail /></AppShell>
        </RequireTenant>
      </RequireAuth>
    ),
  },
  { path: "*", element: <Navigate to="/login" replace /> },
])
```

- [ ] **Step 3: Verify build**

- [ ] **Step 4: Commit**

```bash
git add frontend/src/router.tsx
git commit -m "feat(frontend): wire up /clients and /clients/:id routes"
```

---

## Task 13: Phase B acceptance test (manual + automated)

**Files:** No code changes — verification only.

- [ ] **Step 1: Run all frontend tests**

```bash
cd "C:/project/Hishab AI/frontend" && npm run test
```

Expected: 13 Zod schema tests pass. Build also passes.

- [ ] **Step 2: Verify production build still works**

```bash
npm run build
```

Expected: success.

- [ ] **Step 3: Manual browser smoke test (HUMAN STEP)**

The implementer can describe these steps; the human user verifies:

1. With backend + frontend running locally and `frontend/.env.local` filled in, sign in.
2. Click "Clients" in the sidebar → land on empty list with "No clients yet" empty state.
3. Click "Add client" → fill in Name="Test Co", entity_type=Company, BIN=123456789, is_vat_registered=true → submit.
4. Toast shows "Test Co added (3 compliance events generated)" (or similar count). Client appears in list.
5. Click the client name → land on ClientDetail page → see profile cards with all fields.
6. Add 4 more clients with different entity_types (individual with TIN, partnership, ngo, bank).
7. Search "test" in the list → only matching clients show.
8. Edit a client (change name) → list updates.
9. Delete a client → it disappears.

**Verify in Supabase Dashboard SQL Editor:**

```sql
-- 5 clients, 1 soft-deleted
SELECT name, entity_type, deleted_at FROM clients ORDER BY created_at;

-- Compliance events generated for each client
SELECT c.name, COUNT(e.*) AS event_count
FROM clients c LEFT JOIN compliance_events e ON e.client_id = c.id
WHERE c.deleted_at IS NULL
GROUP BY c.name ORDER BY c.name;

-- Audit log captured the operations (user_id should NOT be null since these came from frontend with JWT)
SELECT action, table_name, user_id IS NOT NULL AS user_captured, created_at
FROM audit_log ORDER BY created_at DESC LIMIT 20;
```

Expected:
- All 5 clients in clients table; 1 has `deleted_at` set
- Each client has multiple compliance_events (varies by entity_type and is_vat_registered)
- Audit log entries exist for each insert/update/delete with `user_captured = true`

- [ ] **Step 4: Tag the Phase B milestone**

```bash
cd "C:/project/Hishab AI"
git tag -a phase-b-complete -m "Phase B clients module complete: CRUD + soft delete + auto-generated compliance events"
```

- [ ] **Step 5: Done**

Phase B is complete. Next: write Phase C plan (reconciliation engine — the hero).

---

## Self-review notes

**Spec coverage check (against [`docs/superpowers/specs/2026-05-02-hishabai-mvp-design.md`](../specs/2026-05-02-hishabai-mvp-design.md)):**

- ✅ Section 3.1 #2 (Clients CRUD: add/edit/soft-delete with name, BIN/TIN, entity type, fiscal year end, search) → Tasks 2-12
- ✅ Section 9 routes `/clients` and `/clients/:id` → Tasks 10, 11, 12
- ✅ Section 8 `generate_compliance_events` invocation on client create → Task 3 (`useCreateClient`)
- ✅ BIN/TIN format validation via Zod → Task 2 (schema + tests)
- ✅ Soft delete via `deleted_at` column → Task 3 (`useDeleteClient`) + Task 7 (confirmation UI) + Task 3 list filter `is("deleted_at", null)`
- ✅ Frontend → Supabase direct (no backend) → all tasks use `supabase` client only
- ⏳ Tabs on ClientDetail (Reconciliations, Documents, Calendar) — scaffolded as "Coming in later phases" placeholder text in Task 11. The tabs themselves come in Phases C/D.

**Type/method consistency:**
- `Client` type defined in Task 2, consumed in Tasks 3, 4, 6, 7, 9, 11 — same shape throughout.
- `ClientFormInput` type defined in Task 2, consumed in Tasks 3, 4, 5, 6 — consistent.
- `ENTITY_TYPES` and `EntityType` defined in Task 2, consumed in Tasks 4, 8 — consistent.
- `useClientsList`, `useClient`, `useCreateClient`, `useUpdateClient`, `useDeleteClient` defined in Task 3, consumed in Tasks 5, 6, 7, 9, 10, 11 — consistent signatures.

**Placeholder scan:** None. Every code step contains the actual code.

**One risk worth flagging:** Task 3 step 2 mentions a possible refactor depending on whether the auth store exposes `tenantId`. The actual auth store from Phase A only stores `session`/`user`/`isLoading`. The implementer should use `useUserProfile()` to get `tenant_id` rather than expecting it on the auth store. Documented inline in Task 3 step 2.
