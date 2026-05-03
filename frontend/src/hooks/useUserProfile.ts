import { useQuery } from "@tanstack/react-query"

import { supabase } from "@/lib/supabase"
import { useAuthStore } from "@/store/auth"

export interface UserProfile {
  id: string
  tenant_id: string
  full_name: string
  role: string
  created_at: string
}

/**
 * Returns the user_profile row for the currently authenticated user.
 * Returns null (not undefined) if the user has no profile yet (pre-onboarding).
 */
export function useUserProfile() {
  const userId = useAuthStore((s) => s.user?.id)

  return useQuery({
    queryKey: ["user_profile", userId],
    enabled: Boolean(userId),
    queryFn: async (): Promise<UserProfile | null> => {
      if (!userId) return null
      const { data, error } = await supabase
        .from("user_profiles")
        .select("*")
        .eq("id", userId)
        .maybeSingle()
      if (error) throw error
      return (data as UserProfile | null) ?? null
    },
  })
}
