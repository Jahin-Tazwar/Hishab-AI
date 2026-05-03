import type { ReactNode } from "react"
import { Navigate } from "react-router-dom"

import { useAuthStore } from "@/store/auth"

interface Props {
  children: ReactNode
}

export function RequireAuth({ children }: Props) {
  const session = useAuthStore((s) => s.session)
  const isLoading = useAuthStore((s) => s.isLoading)

  if (isLoading) return <div className="p-8 text-slate-500">Loading…</div>
  if (!session) return <Navigate to="/login" replace />
  return <>{children}</>
}
