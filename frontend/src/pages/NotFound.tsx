import { Link } from "react-router-dom"

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
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
      <div className="w-full max-w-md rounded-lg border border-slate-200 bg-white p-6 text-center shadow-sm">
        <p className="text-sm font-medium uppercase tracking-wide text-slate-500">
          Error 404
        </p>
        <h1 className="mt-1 text-2xl font-bold text-slate-900">Page not found</h1>
        <p className="mt-2 text-sm text-slate-600">
          The page you're looking for doesn't exist or has been moved.
        </p>
        <div className="mt-5">
          <Link
            to={isAuthed ? "/dashboard" : "/login"}
            className="inline-flex items-center justify-center rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
          >
            {isAuthed ? "Back to dashboard" : "Back to login"}
          </Link>
        </div>
      </div>
    </div>
  )
}
