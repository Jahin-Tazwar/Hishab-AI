import {
  createBrowserRouter,
  Navigate,
  ScrollRestoration,
  useParams,
} from "react-router-dom"

import { AppShell } from "@/components/layout/AppShell"
import { AuthLayout } from "@/components/layout/AuthLayout"
import { RouteBoundary } from "@/components/ErrorBoundary"
import { RequireAuth } from "@/components/RequireAuth"
import { RequireTenant } from "@/components/RequireTenant"
import { ClientDetail } from "@/pages/ClientDetail"
import { Clients } from "@/pages/Clients"
import { Dashboard } from "@/pages/Dashboard"
import { IngestionJob } from "@/pages/IngestionJob"
import { IngestionNew } from "@/pages/IngestionNew"
import { Login } from "@/pages/Login"
import { NotFound } from "@/pages/NotFound"
import { Onboard } from "@/pages/Onboard"
import { ReconReport } from "@/pages/ReconReport"
import { Signup } from "@/pages/Signup"

function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <ScrollRestoration />
      {children}
    </>
  )
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <RequireTenant>
        <AppShell>
          <RouteBoundary>{children}</RouteBoundary>
        </AppShell>
      </RequireTenant>
    </RequireAuth>
  )
}

function RedirectReconNew() {
  const { id } = useParams<{ id: string }>()
  return <Navigate to={`/clients/${id}/ingestion/new`} replace />
}

export const router = createBrowserRouter([
  { path: "/", element: <RootLayout><Navigate to="/login" replace /></RootLayout> },
  { path: "/login", element: <RootLayout><AuthLayout><Login /></AuthLayout></RootLayout> },
  { path: "/signup", element: <RootLayout><AuthLayout><Signup /></AuthLayout></RootLayout> },
  {
    path: "/onboard",
    element: <RootLayout><RequireAuth><AuthLayout><Onboard /></AuthLayout></RequireAuth></RootLayout>,
  },
  { path: "/dashboard", element: <RootLayout><ProtectedRoute><Dashboard /></ProtectedRoute></RootLayout> },
  { path: "/clients", element: <RootLayout><ProtectedRoute><Clients /></ProtectedRoute></RootLayout> },
  { path: "/clients/:id", element: <RootLayout><ProtectedRoute><ClientDetail /></ProtectedRoute></RootLayout> },

  // Ingestion (new flow)
  {
    path: "/clients/:id/ingestion/new",
    element: <RootLayout><ProtectedRoute><IngestionNew /></ProtectedRoute></RootLayout>,
  },
  {
    path: "/clients/:id/ingestion/:jobId",
    element: <RootLayout><ProtectedRoute><IngestionJob /></ProtectedRoute></RootLayout>,
  },

  // Old recon-new → redirect to new ingestion flow
  {
    path: "/clients/:id/recon/new",
    element: <RedirectReconNew />,
  },

  // Recon report still served from the old page
  {
    path: "/clients/:id/recon/:reconId",
    element: <RootLayout><ProtectedRoute><ReconReport /></ProtectedRoute></RootLayout>,
  },

  { path: "*", element: <RootLayout><NotFound /></RootLayout> },
])
