import type { ReactNode } from "react"
import { Link, useLocation } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { supabase } from "@/lib/supabase"
import { useUserProfile } from "@/hooks/useUserProfile"

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

  return (
    <div className="min-h-screen flex">
      <aside className="w-56 border-r bg-slate-50 p-4 flex flex-col">
        <div className="mb-8">
          <h1 className="text-xl font-bold text-slate-900">HishabAI</h1>
          {profile && <p className="text-xs text-slate-500 mt-1">{profile.full_name}</p>}
        </div>
        <nav className="flex flex-col gap-1 flex-1">
          {NAV.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              className={`px-3 py-2 rounded text-sm ${
                location.pathname.startsWith(item.to)
                  ? "bg-slate-900 text-white"
                  : "text-slate-700 hover:bg-slate-200"
              }`}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <Button variant="ghost" size="sm" onClick={() => supabase.auth.signOut()}>
          Sign out
        </Button>
      </aside>
      <main className="flex-1 p-8 bg-white">{children}</main>
    </div>
  )
}
