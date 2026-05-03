import type { ReactNode } from "react"

import { useSessionInit } from "@/hooks/useSession"
import { Toaster } from "@/components/ui/sonner"

interface Props {
  children: ReactNode
}

/**
 * Root wrapper that initializes the auth session subscription.
 * Renders children + the global toast container.
 */
export function AppRoot({ children }: Props) {
  useSessionInit()
  return (
    <>
      {children}
      <Toaster />
    </>
  )
}
