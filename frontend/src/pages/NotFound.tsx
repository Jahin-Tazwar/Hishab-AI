import { Link } from "react-router-dom"

import { Card, CardContent } from "@/components/ui/card"
import { useAuthStore } from "@/store/auth"

/**
 * Catch-all 404 page rendered for any unrecognized route. Picks its target
 * link based on auth state — authenticated users go to /dashboard, others
 * to /login. We don't try to render this inside <AppShell> for authed users
 * because the route entry in router.tsx is the catch-all and isn't wrapped
 * in <RequireAuth>; rendering bare keeps the page reachable when auth is
 * uncertain.
 */
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
            <Link
              to={isAuthed ? "/dashboard" : "/login"}
              className="inline-flex items-center justify-center rounded-lg bg-primary text-primary-foreground px-3 py-1.5 text-sm font-medium hover:bg-primary/90"
            >
              {isAuthed ? "Back to dashboard" : "Back to login"}
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
