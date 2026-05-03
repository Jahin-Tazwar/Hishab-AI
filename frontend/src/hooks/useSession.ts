import { useEffect } from "react"

import { supabase } from "@/lib/supabase"
import { useAuthStore } from "@/store/auth"

/**
 * Initializes the auth store from Supabase on mount and subscribes to auth changes.
 * Call this once at the top of the app.
 */
export function useSessionInit(): void {
  const setSession = useAuthStore((s) => s.setSession)

  useEffect(() => {
    // 1. Initial session fetch
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
    })

    // 2. Subscribe to auth state changes
    const { data: subscription } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session)
    })

    return () => {
      subscription.subscription.unsubscribe()
    }
  }, [setSession])
}
