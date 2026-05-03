import type { ReactNode } from "react"
import { Navigate } from "react-router-dom"

import { useUserProfile } from "@/hooks/useUserProfile"

interface Props {
  children: ReactNode
}

/**
 * Wraps routes that require an onboarded user (one with a user_profile + tenant).
 * Redirects to /onboard if the user is logged in but has no profile yet.
 */
export function RequireTenant({ children }: Props) {
  const { data: profile, isLoading } = useUserProfile()

  if (isLoading) return <div className="p-8 text-slate-500">Loading…</div>
  if (!profile) return <Navigate to="/onboard" replace />
  return <>{children}</>
}
