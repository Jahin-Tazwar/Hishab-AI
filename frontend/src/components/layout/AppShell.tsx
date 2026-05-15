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
