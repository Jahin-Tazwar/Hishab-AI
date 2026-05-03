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
